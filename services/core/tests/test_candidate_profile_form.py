"""E20-4: ручная форма профиля `PATCH /candidates/me/profile`."""

import asyncio

import fakeredis
import pytest
from app.candidates.models import Candidate
from app.config import Settings
from app.graph.models import Evidence
from app.graph.recompute import recompute_profile
from app.graph.trust import TrustConfig
from app.main import build_app
from app.taxonomy.models import Skill
from fastapi.testclient import TestClient
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import select

PWD = "correct-horse-battery"


@pytest.fixture
def c(db_path):
    url = f"sqlite+aiosqlite:///{db_path}"  # копия шаблона с миграциями (conftest)
    app = build_app(Settings(database_url=url, ui_bus_enabled=False))
    factory = make_session_factory(make_engine(url))

    async def seed():
        async with session_scope(factory) as s:
            for slug, kind in [("python", "hard"), ("docker", "hard"), ("teamwork", "soft")]:
                s.add(Skill(slug=slug, name=slug.title(), kind=kind, source="core"))

    asyncio.run(seed())
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.factory = factory
        yield client


def _user(c, email, consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def _q(c, fn):
    async def go():
        async with session_scope(c.factory) as s:
            return await fn(s)

    return asyncio.run(go())


def _patch(c, h, body):
    return c.patch("/candidates/me/profile", json=body, headers=h)


def _recompute(c):
    """Пересчёт профиля, который в проде делает воркер по команде `core.recompute`."""

    async def go(s):
        for cand in list(await s.scalars(select(Candidate))):
            await recompute_profile(s, cand.user_id, None, TrustConfig.load())

    _q(c, go)


def test_form_saves_everything_and_get_returns_it(c):
    h = _user(c, "a@x.io")
    body = {
        "contacts": {"email": "me@ex.io", "telegram": "@me_tg1"},
        "stack": [{"slug": "python", "years": 3}, {"slug": "docker"}],
        "experience_months": 40,
        "desired_roles": ["backend", "devops", "backend"],
        "soft_skills": ["teamwork"],
    }
    r = _patch(c, h, body)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["contacts"] == {"email": "me@ex.io", "phone": None, "telegram": "@me_tg1"}
    assert p["desired_roles"] == ["backend", "devops"]
    assert p["experience_months"] == 40 and p["claimed_soft"] == ["Teamwork"]
    _recompute(c)
    got = c.get("/candidates/me/profile", headers=h).json()
    assert got["contacts"] == p["contacts"]
    assert {s["skill"]["slug"] for s in got["skills"]} == {"python", "docker"}
    assert all(s["claimed_only"] for s in got["skills"])  # «заявлено», без подтверждения

    async def rows(s):
        ev = list(await s.scalars(select(Evidence)))
        cand = (await s.scalars(select(Candidate))).one()
        return ev, cand

    ev, cand = _q(c, rows)
    assert {(e.source, e.strength, e.verified) for e in ev} == {("self", 0.15, False)}
    assert b"me@ex.io" not in cand.contacts_enc  # ПДн в БД зашифрованы


def test_partial_patch_keeps_rest_and_stack_replace(c):
    h = _user(c, "a@x.io")
    _patch(c, h, {"stack": [{"slug": "python"}, {"slug": "docker"}], "desired_roles": ["qa"]})
    p = _patch(c, h, {"stack": [{"slug": "python"}]}).json()
    assert p["desired_roles"] == ["qa"]
    _recompute(c)
    p = c.get("/candidates/me/profile", headers=h).json()
    assert {s["skill"]["slug"] for s in p["skills"]} == {"python"}
    assert _patch(c, h, {"contacts": None}).json()["contacts"] is None


def test_repeat_is_idempotent_no_new_events(c):
    h = _user(c, "a@x.io")
    body = {"stack": [{"slug": "python"}], "experience_months": 12, "soft_skills": ["teamwork"]}
    _patch(c, h, body)

    async def snap(s):
        n_ev = len(list(await s.scalars(select(Evidence))))
        n_out = len(list(await s.scalars(select(OutboxRecord))))
        return n_ev, n_out

    first = _q(c, snap)
    _patch(c, h, body)
    assert _q(c, snap) == first


def test_recompute_requested_and_version_bumps(c):
    h = _user(c, "a@x.io")
    v0 = c.get("/candidates/me/profile", headers=h).json()["profile_version"]

    async def recomputes(s):
        return [r for r in await s.scalars(select(OutboxRecord)) if "recompute" in str(r.type)]

    _patch(c, h, {"experience_months": 24})
    assert len(_q(c, recomputes)) == 1
    assert c.get("/candidates/me/profile", headers=h).json()["profile_version"] >= v0


def test_validation_errors(c):
    h = _user(c, "a@x.io")
    r = _patch(c, h, {"stack": [{"slug": "nope"}]})
    assert r.status_code == 422 and r.json()["code"] == "unknown_skill"
    assert _patch(c, h, {"stack": [{"slug": "teamwork"}]}).status_code == 422  # софт не в стеке
    assert _patch(c, h, {"soft_skills": ["python"]}).status_code == 422  # стек не в софте
    assert _patch(c, h, {"contacts": {"email": "bad"}}).status_code == 422
    assert _patch(c, h, {"experience_months": -1}).status_code == 422
    assert _patch(c, h, {"desired_roles": ["wizard"]}).status_code == 422
    assert _patch(c, h, {"unknown": 1}).status_code == 422


def test_auth_and_consent(c):
    assert c.patch("/candidates/me/profile", json={}).status_code == 401
    h = _user(c, "b@x.io", consent=False)
    r = _patch(c, h, {"experience_months": 1})
    assert r.status_code == 403 and r.json()["code"] == "consent_required"
    emp = c.post("/auth/register", json={"email": "e@x.io", "password": PWD, "role": "employer"})
    eh = {"Authorization": f"Bearer {emp.json()['access_token']}"}
    assert _patch(c, eh, {}).status_code == 403


def test_users_are_isolated(c):
    a, b = _user(c, "a@x.io"), _user(c, "b@x.io")
    _patch(c, a, {"contacts": {"email": "a@ex.io"}, "stack": [{"slug": "python"}]})
    _recompute(c)
    pb = c.get("/candidates/me/profile", headers=b).json()
    assert pb["contacts"] is None and pb["skills"] == []
