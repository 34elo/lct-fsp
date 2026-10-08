import json
import subprocess
import sys
from pathlib import Path

import fakeredis
import httpx
import pytest
from app.config import Settings
from app.fsp.client import ConnectorClient
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
CALLS: list[tuple[str, str, dict]] = []


def _connector(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else {}
    CALLS.append((request.method, request.url.path, body))
    assert request.headers["authorization"] == "Service tok"
    p = request.url.path
    if p == "/internal/oauth/authorize-url":
        return httpx.Response(
            200, json={"url": "http://mock/authorize?state=" + request.url.params["state"]}
        )
    if p == "/internal/oauth/exchange":
        if body["code"] == "bad":
            return httpx.Response(502, json={"code": "fsp_auth_error", "title": "x"})
        return httpx.Response(200, json={"participant_id": "p-anya", "verified": True})
    if p == "/internal/links":
        if body["participant_id"] == "nobody":
            return httpx.Response(404, json={"code": "fsp_not_found", "title": "нет"})
        return httpx.Response(200, json={"method": "code", "masked_contact": "a***@x.ru"})
    if p == "/internal/links/verify":
        return httpx.Response(200, json={"verified": body["code"] == "123456"})
    return httpx.Response(404)


@pytest.fixture
def c(tmp_path):
    CALLS.clear()
    db = tmp_path / "c.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False,
                             web_base_url="http://web"))  # fmt: skip
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.fsp_client = ConnectorClient(
            "http://fspc", "tok", transport=httpx.MockTransport(_connector)
        )
        client.app_ = app
        yield client


def _user(c, email, role="candidate", consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def test_oauth_start_callback_roundtrip(c):
    h = _user(c, "a@x.io")
    r = c.get("/auth/fsp/start", headers=h)
    assert r.status_code == 200
    state = r.json()["url"].split("state=")[1]
    cb = c.get("/auth/fsp/callback", params={"code": "ok", "state": state}, follow_redirects=False)
    assert cb.status_code == 302 and cb.headers["location"] == "http://web/me?fsp=linked"
    exch = [x for x in CALLS if x[1].endswith("exchange")][0][2]
    assert exch["code"] == "ok" and exch["code_verifier"]
    # state одноразовый
    again = c.get(
        "/auth/fsp/callback", params={"code": "ok", "state": state}, follow_redirects=False
    )
    assert "fsp=error" in again.headers["location"] and "state_invalid" in again.headers["location"]


def test_oauth_callback_connector_error_and_denied(c):
    h = _user(c, "a@x.io")
    s1 = c.get("/auth/fsp/start", headers=h).json()["url"].split("state=")[1]
    r = c.get("/auth/fsp/callback", params={"code": "bad", "state": s1}, follow_redirects=False)
    assert "reason=fsp_auth_error" in r.headers["location"]
    s2 = c.get("/auth/fsp/start", headers=h).json()["url"].split("state=")[1]
    r = c.get(
        "/auth/fsp/callback", params={"error": "access_denied", "state": s2}, follow_redirects=False
    )
    assert "reason=denied" in r.headers["location"]


def test_start_requires_candidate(c):
    assert c.get("/auth/fsp/start").status_code == 401
    anon = c.get("/auth/fsp/start", params={"redirect": "true"}, follow_redirects=False)
    assert anon.status_code == 302 and anon.headers["location"].startswith("/login")
    e = _user(c, "e@x.io", role="employer")
    assert c.get("/auth/fsp/start", headers=e).status_code == 403
    h = _user(c, "a@x.io")
    r = c.get("/auth/fsp/start", params={"redirect": "true"}, headers=h, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("http://mock/")


def test_link_verify_and_errors(c):
    h = _user(c, "a@x.io")
    r = c.post("/candidates/me/fsp/link", json={"participant_id": "p-anya"}, headers=h)
    assert r.json() == {"method": "code", "masked_contact": "a***@x.ru"}
    assert c.post("/candidates/me/fsp/link", json={}, headers=h).status_code == 422
    nf = c.post("/candidates/me/fsp/link", json={"participant_id": "nobody"}, headers=h)
    assert nf.status_code == 404 and nf.json()["code"] == "fsp_not_found"
    assert c.post("/candidates/me/fsp/verify", json={"code": "000000"}, headers=h).json() == {
        "verified": False
    }
    assert c.post("/candidates/me/fsp/verify", json={"code": "123456"}, headers=h).json() == {
        "verified": True
    }


def test_rights_and_no_consent(c):
    body = {"participant_id": "p-anya"}
    assert c.post("/candidates/me/fsp/link", json=body).status_code == 401
    e = _user(c, "e@x.io", role="employer")
    assert c.post("/candidates/me/fsp/link", json=body, headers=e).status_code == 403
    assert c.get("/candidates/me/fsp", headers=e).status_code == 403
    nc = _user(c, "n@x.io", consent=False)
    assert c.post("/candidates/me/fsp/link", json=body, headers=nc).status_code == 403


def test_overview_empty_and_sync_requires_link(c):
    h = _user(c, "a@x.io")
    o = c.get("/candidates/me/fsp", headers=h).json()
    assert o == {"link": {"linked": False, "verified": False, "participant_id": None},
                 "achievements": [], "ranks": [], "teams": []}  # fmt: skip
    assert c.post("/candidates/me/fsp/sync", headers=h).status_code == 409


def test_sync_throttled_and_outbox(c):
    import asyncio

    from app.graph.fsp_models import FspParticipant
    from fsp_platform.db import session_scope

    h = _user(c, "a@x.io")
    uid = c.get("/me", headers=h).json()["id"]
    c.get("/candidates/me/fsp", headers=h)  # создаёт анкету

    async def link():
        import uuid

        async with session_scope(c.app_.state.session_factory) as s:
            s.add(
                FspParticipant(candidate_id=uuid.UUID(uid), participant_id="p-anya", verified=True)
            )

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(link())
    assert c.get("/candidates/me/fsp", headers=h).json()["link"]["linked"] is True
    assert c.post("/candidates/me/fsp/sync", headers=h).status_code == 202
    assert c.post("/candidates/me/fsp/sync", headers=h).status_code == 429
