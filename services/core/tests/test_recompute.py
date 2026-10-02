import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.config import Settings
from app.graph import service
from app.graph.models import CandidateSkill
from app.graph.recompute import recompute_profile
from app.graph.service import EvidenceIn
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy.models import Skill
from app.worker import Worker
from fsp_contracts import new_envelope
from fsp_contracts.commands import CoreRecompute
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
CFG = TrustConfig.load()
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
D = NOW.date()


@pytest.fixture
def db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'r.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
def factory(db):
    return make_session_factory(make_engine(db))


async def _seed(factory, status="active"):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        sk = Skill(slug=f"py-{uid.hex[:6]}", name="py", kind="hard", source="core", status=status)
        s.add(sk)
        await s.flush()
        return uid, sk.id


def _ev(skill, source, strength, fact=None, observed=D, **kw):
    return EvidenceIn(skill, source, strength, observed, "fact", fact or uuid.uuid4(), **kw)


async def _rows(s, uid):
    return list(await s.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == uid)))


async def _count(s, typ):
    return await s.scalar(
        select(func.count()).select_from(OutboxRecord).where(OutboxRecord.type == typ)
    )


async def test_recompute_builds_candidate_skills_and_event(factory):
    uid, py = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "github", 0.5), _ev(py, "resume", 0.3)])
    async with session_scope(factory) as s:
        res = await recompute_profile(s, uid, None, CFG, now=NOW)
        assert res.changed and res.profile_version == 1
    async with session_scope(factory) as s:
        (row,) = await _rows(s, uid)
        assert (row.confidence, row.level, row.claimed_only) == (0.65, 3, False)
        assert row.sources == ["github", "resume"] and len(row.top_evidence) == 2
        ev = (
            await s.scalars(
                select(OutboxRecord).where(OutboxRecord.type == "skills.profile.updated")
            )
        ).one()
        p = ev.payload["payload"]
        assert p["profile_version"] == 1 and p["diff"]["skills_new"][0]["to"] == 3


async def test_unchanged_recompute_keeps_version_and_emits_nothing(factory):
    uid, py = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
        await recompute_profile(s, uid, None, CFG, now=NOW)
    async with session_scope(factory) as s:
        res = await recompute_profile(s, uid, None, CFG, now=NOW + timedelta(hours=1))
        assert not res.changed and res.profile_version == 1
        assert await _count(s, "skills.profile.updated") == 1


async def test_level_up_diff_decay_and_removal(factory):
    uid, py = await _seed(factory)
    f = uuid.uuid4()
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "resume", 0.3, f)])
        await recompute_profile(s, uid, None, CFG, now=NOW)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
        await recompute_profile(s, uid, None, CFG, now=NOW + timedelta(seconds=1))
        events = (
            await s.scalars(
                select(OutboxRecord)
                .where(OutboxRecord.type == "skills.profile.updated")
                .order_by(OutboxRecord.id)
            )
        ).all()
        up = events[-1].payload["payload"]["diff"]["skills_up"]
        assert up[0]["from"] == 1 and up[0]["to"] == 4
    async with session_scope(factory) as s:  # затухание ФСП на 3 года: 0.45, с резюме 0.615
        later = NOW + timedelta(days=round(365.25 * 3))
        await recompute_profile(s, uid, None, CFG, now=later)
        (row,) = await _rows(s, uid)
        assert row.level == 3 and row.confidence == pytest.approx(0.615, abs=1e-3)
    async with session_scope(factory) as s:  # доказательства деактивированы -> строка исчезла
        await service.deactivate(s, uid, source="fsp")
        await service.deactivate(s, uid, source="resume")
        await recompute_profile(s, uid, None, CFG, now=NOW + timedelta(days=2000))
        assert await _rows(s, uid) == []


async def test_provisional_skill_capped(factory):
    uid, py = await _seed(factory, status="provisional")
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
        await recompute_profile(s, uid, None, CFG, now=NOW)
        (row,) = await _rows(s, uid)
        assert row.confidence == 0.25 and row.level == 1


async def test_merge_by_requested_at(factory):
    uid, py = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
        await recompute_profile(s, uid, None, CFG, now=NOW)
    async with session_scope(factory) as s:
        old = await recompute_profile(s, uid, NOW - timedelta(seconds=5), CFG, now=NOW)
        eq = await recompute_profile(s, uid, NOW, CFG, now=NOW)
        assert old.skipped and eq.skipped
        fresh = await recompute_profile(s, uid, NOW + timedelta(seconds=1), CFG, now=NOW)
        assert not fresh.skipped


async def test_writer_requests_recompute_command(factory):
    uid, py = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
        cmd = (
            await s.scalars(select(OutboxRecord).where(OutboxRecord.type == "core.recompute"))
        ).one()
        cand = await s.get(Candidate, uid)
        assert cmd.payload["payload"]["candidate_id"] == str(uid)
        assert cand.recompute_requested_at is not None


async def test_recompute_handler_redelivery_and_taxonomy(db, factory):
    uid, py = await _seed(factory)
    other, _ = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, "fsp", 0.9)])
    worker = Worker(Settings(database_url=db))
    env = new_envelope(
        "core.recompute",
        "core",
        CoreRecompute(candidate_id=uid, requested_at=datetime.now(UTC)),
    )
    consumer = worker.consumers["core.recompute"]
    await consumer.dispatch(env)
    await consumer.dispatch(env)  # повторная доставка
    async with session_scope(factory) as s:
        assert len(await _rows(s, uid)) == 1
        assert (await s.get(Candidate, uid)).profile_version == 1
        assert await _count(s, "skills.profile.updated") == 1
        assert await _rows(s, other) == []
        before = await _count(s, "core.recompute")
    tax = new_envelope("taxonomy.updated", "core", {"version": 2, "changed_skill_ids": [str(py)]})
    await worker.consumers["core.handlers"].dispatch(tax)
    async with session_scope(factory) as s:
        assert await _count(s, "core.recompute") == before + 1  # только затронутый кандидат
    await worker.engine.dispose()
