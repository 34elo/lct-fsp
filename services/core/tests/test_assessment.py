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
from app.taxonomy.models import Role
from fsp_contracts.assessment import CategoryChanged, SkillType, TestGrade
from fsp_contracts.registry import EVENTS
from fsp_platform.app import ProblemError
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select, update

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
    # все профессии открыты (E39-6, отменяет скрытие E36-2)
    assert set(profs) == {"backend", "frontend", "ai_engineer", "mobile", "ml", "devops", "qa"}
    async with session_scope(factory) as s:
        await s.execute(update(Role).where(Role.slug == "ml").values(is_active=False))
    async with session_scope(factory) as s:
        assert "ml" not in {p.slug for p in await tax.list_professions(s)}  # флаг скрытия работает
        every = {p.slug: p for p in await tax.list_professions(s, include_hidden=True)}
    assert set(every) == set(profs)
    assert not every["ml"].active and every["ml"].skill_weights  # скрыта, данные на месте
    be = profs["backend"]
    assert be.title and be.skill_weights and all(0 < w <= 1 for w in be.skill_weights.values())
    assert "python" in be.skill_weights
    assert set(be.skill_types) == set(be.skill_weights)
    assert be.skill_types["python"] == SkillType.hard
    assert be.skill_types["algorithms"] == SkillType.fundamental
    assert be.skill_types["debugging"] == SkillType.thinking
    # каждая профессия покрывает все шесть типов навыков
    for p in profs.values():
        assert set(p.skill_types.values()) == set(SkillType), p.slug
    assert {"rag", "llm_serving"} <= set(profs["ai_engineer"].skill_weights)


async def test_professions_endpoint(factory, db_url):
    from app.config import Settings
    from app.main import build_app
    from fastapi.testclient import TestClient

    data = load_taxonomy(CORE.parents[1] / "data" / "taxonomy")
    async with session_scope(factory) as s:
        await tax.sync(s, data)
    app = build_app(Settings(database_url=db_url, ui_bus_enabled=False))
    with TestClient(app) as c:
        r = c.get("/taxonomy/professions")
    assert r.status_code == 200
    body = r.json()
    # все профессии открыты (E39-6); тонкий банк — «бета», у ядра MVP банк полный
    profs = {p["slug"]: p for p in body["professions"]}
    assert set(profs) == {"ai_engineer", "backend", "devops", "frontend", "ml", "mobile", "qa"}
    assert all(p["active"] for p in profs.values())
    assert not any(profs[s]["beta"] for s in ("backend", "frontend", "ai_engineer"))
    assert profs["mobile"]["beta"]
    assert body["skill_types"] == [t.value for t in SkillType]
    assert body["grades"] == [
        {"grade": "junior", "cut": -1.0},
        {"grade": "middle", "cut": 0.0},
        {"grade": "senior", "cut": 1.0},
    ]


def test_loader_skill_types_and_coverage(tmp_path):
    import yaml
    from app.taxonomy.loader import TaxonomyError

    def build(profession_skills, types=None):
        d = tmp_path / "t"
        d.mkdir(exist_ok=True)
        skills = [
            {"slug": "a", "name": "A", "kind": "hard"},
            {"slug": "b", "name": "B", "kind": "soft"},
            {"slug": "c", "name": "C", "kind": "domain", "group": "fundamentals"},
            {"slug": "d", "name": "D", "kind": "hard"},
            {"slug": "e", "name": "E", "kind": "hard"},
            {"slug": "f", "name": "F", "kind": "hard"},
        ]
        doc = {
            "skills": skills,
            "roles": [
                {"slug": "dev", "name": "Dev", "profession": True, "skills": profession_skills}
            ],
        }
        if types:
            doc["skill_types"] = types
        (d / "x.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        return load_taxonomy(d)

    with pytest.raises(TaxonomyError, match="нет навыков типов"):
        build({"a": 1.0, "b": 1.0, "c": 1.0})
    data = build(
        {"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0, "e": 1.0, "f": 1.0},
        [
            {"type": "thinking", "skills": ["d"]},
            {"type": "business", "skills": ["e"]},
            {"type": "experience", "skills": ["f"]},
        ],
    )
    assert (
        data.skill_types["a"] == SkillType.hard and data.skill_types["c"] == SkillType.fundamental
    )
    assert data.skill_types["f"] == SkillType.experience
    with pytest.raises(TaxonomyError, match="два разных типа"):
        build(
            {"a": 1.0},
            [{"type": "thinking", "skills": ["a"]}, {"type": "soft", "skills": ["a"]}],
        )
    with pytest.raises(TaxonomyError, match="неизвестные навыки"):
        build({"a": 1.0}, [{"type": "soft", "skills": ["zzz"]}])


def test_real_scoring_grade_cuts():
    from app.taxonomy.loader import load_grade_cuts

    cuts = load_grade_cuts(CORE.parents[1] / "data" / "scoring.yaml")
    assert cuts == {"junior": -1.0, "middle": 0.0, "senior": 1.0}


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


async def test_claimed_vs_confirmed_resume_old_scale(factory):
    """Старая шкала резюме сворачивается к шкале теста; опрос приоритетнее резюме."""
    async with session_scope(factory) as s:
        lead = await _cand(s, primary_role="backend", grade="lead")
        await svc.seed_grade(s, lead, "backend", "middle", 0.5)
        plus = await _cand(s, primary_role="backend", grade="middle_plus")
        await svc.seed_grade(s, plus, "backend", "middle", 0.5)
        jp = await _cand(s, primary_role="backend", grade="junior_plus")
        await svc.seed_grade(s, jp, "backend", "middle", 0.5)
    async with session_scope(factory) as s:
        (r,) = await svc.claimed_vs_confirmed(s, lead)
        assert (r.status, r.resume_grade) == ("overclaimed", "lead")
        (r,) = await svc.claimed_vs_confirmed(s, plus)
        assert r.status == "confirmed"
        (r,) = await svc.claimed_vs_confirmed(s, jp)
        assert r.status == "underclaimed"


async def test_declared_grades_unconfirmed(factory):
    """E32-1 (ADR-025): заявленный грейд из последнего опроса виден, пока нет подтверждения."""
    from app.assessment.models import Survey

    async with session_scope(factory) as s:
        a, b, c = await _cand(s), await _cand(s), await _cand(s)
        # a: middle по backend (последний опрос), подтверждения нет; по ml — подтверждён
        s.add(
            Survey(
                candidate_id=a,
                profession="backend",
                declared_grade="junior",
                created_at=NOW - timedelta(days=2),
            )
        )
        s.add(
            Survey(
                candidate_id=a,
                profession="backend",
                declared_grade="middle",
                created_at=NOW - timedelta(days=1),
            )
        )
        s.add(Survey(candidate_id=a, profession="ml", declared_grade="senior", created_at=NOW))
        await svc.seed_grade(s, a, "ml", "middle", 0.5)
        # b: middle по backend, но грейд истёк — снова «не подтверждён»
        s.add(Survey(candidate_id=b, profession="backend", declared_grade="middle", created_at=NOW))
        await svc.seed_grade(s, b, "backend", "junior", -0.5, now=NOW - timedelta(days=400))
        # c: опрос без заявленного грейда
        s.add(Survey(candidate_id=c, profession="frontend", declared_grade=None, created_at=NOW))
    async with session_scope(factory) as s:
        many = await svc.declared_grades_many(s, [a, b, c])
        assert set(many) == {a, b, c} and many[c] == []
        assert [(d.profession, d.grade) for d in many[a]] == [("backend", TestGrade.middle)]
        assert many[a][0].declared_at.tzinfo is not None
        assert [(d.profession, d.grade) for d in many[b]] == [("backend", TestGrade.middle)]
        assert await svc.declared_grades_many(s, []) == {}
        assert sorted(await svc.declared_members(s, "backend", "middle")) == sorted([a, b])
        assert await svc.declared_members(s, "backend", TestGrade.junior) == []
        assert await svc.declared_members(s, "ml", "senior") == []  # ml подтверждён
        assert await svc.declared_counts(s) == {("backend", "middle"): 2}
        # подтверждённые категории не смешиваются с заявленными
        assert await svc.category_counts(s) == {("ml", "middle"): 1}
