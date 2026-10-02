import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph import service
from app.graph.models import Evidence
from app.graph.service import EvidenceIn
from app.identity.models import User
from app.taxonomy.models import Skill
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
D = date(2025, 5, 1)


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'e.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    engine = make_engine(url)
    yield make_session_factory(engine)


async def _seed(factory):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        skills = []
        for slug in (f"python-{uid.hex[:6]}", f"fastapi-{uid.hex[:6]}"):
            sk = Skill(slug=slug, name=slug, kind="hard", source="core")
            s.add(sk)
            skills.append(sk)
        await s.flush()
        return uid, [sk.id for sk in skills]


async def _events(s):
    return list(
        await s.scalars(select(OutboxRecord).where(OutboxRecord.type == "evidence.changed"))
    )


def _ev(skill, fact, strength=0.9, source="fsp", **kw):
    return EvidenceIn(skill, source, strength, D, "fsp_result", fact, **kw)


async def test_upsert_idempotent(factory):
    uid, (py, _) = await _seed(factory)
    fact = uuid.uuid4()
    async with session_scope(factory) as s:
        r = await service.upsert_evidence(s, uid, [_ev(py, fact, details={"place": 2})])
        assert (r.created, r.updated, r.unchanged) == (1, 0, 0)
    async with session_scope(factory) as s:  # повторная доставка
        r = await service.upsert_evidence(s, uid, [_ev(py, fact, details={"place": 2})])
        assert (r.created, r.updated, r.unchanged) == (0, 0, 1) and not r.changed
    async with session_scope(factory) as s:
        assert await s.scalar(select(func.count()).select_from(Evidence)) == 1
        evs = await _events(s)
        assert len(evs) == 1 and evs[0].payload["payload"]["sources"] == ["fsp"]


async def test_update_changes_and_reactivates(factory):
    uid, (py, _) = await _seed(factory)
    fact = uuid.uuid4()
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, fact)])
    async with session_scope(factory) as s:
        r = await service.upsert_evidence(s, uid, [_ev(py, fact, strength=0.5)])
        assert r.updated == 1
    async with session_scope(factory) as s:
        assert await service.deactivate(s, uid, fact_id=fact) == 1
        assert await service.list_active(s, uid) == []
        assert await service.deactivate(s, uid, fact_id=fact) == 0
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [_ev(py, fact, strength=0.5)])
        rows = await service.list_active(s, uid)
        assert len(rows) == 1 and rows[0].strength == 0.5
        assert len(await _events(s)) == 4  # create, update, deactivate, reactivate


async def test_batch_dedup_and_validation(factory):
    uid, (py, fa) = await _seed(factory)
    fact = uuid.uuid4()
    async with session_scope(factory) as s:
        r = await service.upsert_evidence(
            s, uid, [_ev(py, fact, 0.3), _ev(py, fact, 0.7), _ev(fa, fact, source="github")]
        )
        assert r.created == 2
        assert [e.strength for e in await service.list_active(s, uid, py)] == [0.7]
        assert (await _events(s))[0].payload["payload"]["sources"] == ["fsp", "github"]
        with pytest.raises(ValueError):
            await service.upsert_evidence(s, uid, [_ev(py, uuid.uuid4(), 1.2)])
        with pytest.raises(ValueError):
            await service.deactivate(s, uid)


async def test_candidates_by_skills_and_isolation(factory):
    a, (py, fa) = await _seed(factory)
    b, _ = await _seed(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, a, [_ev(py, uuid.uuid4())])
        await service.upsert_evidence(s, b, [_ev(fa, uuid.uuid4())])
        assert await service.candidates_by_skills(s, [py]) == [a]
        assert await service.candidates_by_skills(s, []) == []
        assert await service.list_active(s, b, py) == []
