"""Граница блока 1: assessment.service (blocks.md §4.3), email (§4.6), профессии, OpenAPI."""

import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.assessment import service as svc
from app.candidates.models import Candidate
from app.identity import service as identity
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from fsp_contracts.assessment import CategoryChanged, TestGrade
from fsp_contracts.registry import EVENTS
from fsp_platform.app import ProblemError
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'a.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
async def factory(db_url):
    return make_session_factory(make_engine(db_url))


async def _cand(s, **kw) -> uuid.UUID:
    uid = uuid.uuid4()
    s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
    s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12], **kw))
    await s.flush()
    return uid


async def test_get_grades_only_active(factory):
    async with session_scope(factory) as s:
        uid = await _cand(s)
        await svc.seed_grade(s, uid, "backend", "middle", 0.4)
        # истёкший грейд не возвращается
        await svc.seed_grade(s, uid, "qa", "junior", -0.5, now=NOW - timedelta(days=400))
    async with session_scope(factory) as s:
        got = await svc.get_grades(s, uid)
        assert [(g.profession, g.grade) for g in got] == [("backend", TestGrade.middle)]
        assert got[0].source == "seed" and got[0].valid_until.tzinfo is not None
        assert await svc.get_grade(s, uid, "qa") is None
        assert (await svc.get_grade(s, uid, "backend")).theta == 0.4
        assert await svc.last_activity_at(s, uid) is not None


async def test_get_grades_many_and_counts(factory):
    async with session_scope(factory) as s:
        a, b, c = await _cand(s), await _cand(s), await _cand(s)
        await svc.seed_grade(s, a, "backend", "junior", -0.6)
        await svc.seed_grade(s, a, "ml", "senior", 1.5)
        await svc.seed_grade(s, b, "backend", "junior", -0.2)
        await svc.seed_grade(s, c, "backend", "middle", 0.5, now=NOW - timedelta(days=500))
    async with session_scope(factory) as s:
        many = await svc.get_grades_many(s, [a, b, c, uuid.uuid4()])
        assert set(many) == {a, b}  # без действующих — ключа нет
        assert len(many[a]) == 2 and len(many[b]) == 1
        assert await svc.get_grades_many(s, []) == {}
        assert sorted(await svc.category_members(s, "backend", TestGrade.junior)) == sorted([a, b])
        assert await svc.category_members(s, "backend", "middle") == []  # у c истёк
        assert await svc.category_counts(s) == {
            ("backend", "junior"): 2,
            ("ml", "senior"): 1,
        }


async def test_seed_grade_upsert_and_outbox_event(factory):
    async with session_scope(factory) as s:
        uid = await _cand(s, profile_version=7)
        g = await svc.seed_grade(
            s, uid, "backend", "junior", -0.5, integrity=0.5, needs_confirmation=True, now=NOW
        )
        assert g.source == "seed" and g.needs_confirmation and g.integrity == 0.5
        assert g.band_position == pytest.approx(0.5)  # junior: (−0.5 − (−1)) / 1
        assert g.valid_until - g.confirmed_at == timedelta(days=365)
        await svc.seed_grade(s, uid, "ml", "senior", 3.0, now=NOW)
        g2 = await svc.seed_grade(s, uid, "backend", "middle", 0.25, now=NOW)  # upsert
        assert g2.grade == TestGrade.middle
    async with session_scope(factory) as s:
        assert len(await svc.get_grades(s, uid)) == 2
        events = list(await s.scalars(select(OutboxRecord).order_by(OutboxRecord.id)))
        assert [e.type for e in events] == ["candidate.category.changed"] * 3
        payload = CategoryChanged.model_validate(events[-1].payload["payload"])
        assert payload.profile_version == 7
        assert {(c.profession, c.grade) for c in payload.categories} == {
            ("backend", TestGrade.middle),
            ("ml", TestGrade.senior),
        }  # полный набор, не дельта
        assert "candidate.category.changed" in EVENTS


async def test_seed_grade_band_position_clamped(factory):
    async with session_scope(factory) as s:
        uid = await _cand(s)
        top = await svc.seed_grade(s, uid, "backend", "senior", 5.0)
        low = await svc.seed_grade(s, uid, "ml", "junior", -3.0)
    assert top.band_position == 1.0 and low.band_position == 0.0


async def test_claimed_vs_confirmed(factory):
    async with session_scope(factory) as s:
        uid = await _cand(s, primary_role="backend", grade="senior")
        await svc.seed_grade(s, uid, "backend", "middle", 0.5)  # заявлено выше
        await svc.seed_grade(s, uid, "qa", "senior", 1.5)  # заявленного нет
        none = await _cand(s, primary_role="ml", grade="middle")  # подтверждения нет
        low = await _cand(s, primary_role="backend", grade="junior")
        await svc.seed_grade(s, low, "backend", "middle", 0.5)
    async with session_scope(factory) as s:
        res = {r.profession: r for r in await svc.claimed_vs_confirmed(s, uid)}
        assert res["backend"].status == "overclaimed"
        assert res["backend"].resume_grade == "senior"
        assert res["backend"].confirmed_grade == TestGrade.middle
        assert res["backend"].declared_grade is None
        assert res["qa"].status == "confirmed"
        (r,) = await svc.claimed_vs_confirmed(s, none)
        assert (r.profession, r.status, r.confirmed_grade) == ("ml", "unconfirmed", None)
        (r,) = await svc.claimed_vs_confirmed(s, low)
        assert r.status == "underclaimed"
        assert await svc.claimed_vs_confirmed(s, uuid.uuid4()) == []


def test_email_verification():
    u = User(email="a@x.io", role="candidate")
    assert identity.is_email_verified(u, required=False)
    assert not identity.is_email_verified(u, required=True)
    identity.require_verified_email(u, required=False)
    with pytest.raises(ProblemError) as e:
        identity.require_verified_email(u, required=True)
    assert e.value.status == 403 and e.value.code == "email_not_verified"
    u.email_verified_at = NOW
    assert identity.is_email_verified(u, required=True)
    identity.require_verified_email(u, required=True)


def test_email_verification_default_off(monkeypatch):
    monkeypatch.delenv("EMAIL_VERIFICATION_REQUIRED", raising=False)
    assert identity.is_email_verified(User(email="a@x.io", role="candidate"))
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED", "true")
    assert not identity.is_email_verified(User(email="a@x.io", role="candidate"))


async def test_list_professions(factory):
    data = load_taxonomy(CORE.parents[1] / "data" / "taxonomy")
    async with session_scope(factory) as s:
        await tax.sync(s, data)
    async with session_scope(factory) as s:
        profs = {p.slug: p for p in await tax.list_professions(s)}
    assert {"backend", "frontend", "mobile", "ml", "devops", "qa"} <= set(profs)
    be = profs["backend"]
    assert be.title and be.skill_weights and all(0 < w <= 1 for w in be.skill_weights.values())
    assert "python" in be.skill_weights and be.skill_types == {}


def test_problem_responses_in_openapi():
    from app.config import Settings
    from app.main import build_app
    from fastapi import APIRouter

    app = build_app(Settings(ui_bus_enabled=False))
    r = APIRouter()

    @r.get("/_p", responses=problem_responses(401, 404))
    async def probe():
        return {}

    app.include_router(r)
    op = app.openapi()["paths"]["/_p"]["get"]["responses"]
    for code in ("401", "404"):
        assert "application/problem+json" in op[code]["content"]
    assert "ProblemOut" in app.openapi()["components"]["schemas"]
    assert problem_responses() == {}
