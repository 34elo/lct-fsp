"""Реестр ФСП: кнопка «Привязать ФСП», заявка, раздел админа; права."""

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import fakeredis
import httpx
import pytest
from app.config import Settings
from app.fsp.client import ConnectorClient
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

PWD = "correct-horse-battery"
CALLS: list[tuple[str, str, dict, dict]] = []
REQ_ID = str(uuid4())
REQ = {
    "id": REQ_ID,
    "candidate_id": str(uuid4()),
    "full_name": "Чужой Человек",
    "email": "other@x.ru",
    "phone": None,
    "event": "Кубок",
    "status": "pending",
    "reason": None,
    "participant_id": None,
    "created_at": "2026-10-09T10:00:00Z",
    "decided_at": None,
}


def _connector(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else {}
    CALLS.append((request.method, request.url.path, body, dict(request.url.params)))
    assert request.headers["authorization"] == "Service tok"
    p, m = request.url.path, request.method
    if p == "/internal/registry/match":
        hit = "jury-candidate@demo.fsp.test" in body["emails"]
        return httpx.Response(
            200,
            json={
                "linked": hit,
                "participant_id": "r-jury" if hit else None,
                "matched_by": "email" if hit else None,
            },  # fmt: skip
        )
    if p.startswith("/internal/registry/requests/by-candidate/"):
        return httpx.Response(200, json=None)
    if p == "/internal/registry/requests" and m == "POST":
        return httpx.Response(201, json=REQ | {"full_name": body["full_name"]})
    if p == "/internal/registry/requests":
        return httpx.Response(200, json=[REQ | {"candidates": []}])
    if p == f"/internal/registry/requests/{REQ_ID}/accept":
        return httpx.Response(200, json=REQ | {"status": "accepted", "participant_id": "r-1"})
    if p.endswith("/accept"):
        return httpx.Response(404, json={"code": "not_found", "title": "Заявка не найдена"})
    if p == "/internal/registry/events" and m == "POST":
        return httpx.Response(201, json=body | {"id": "e-1", "results": 0})
    if p == "/internal/registry/events":
        return httpx.Response(200, json=[])
    if p == "/internal/registry/participants":
        return httpx.Response(200, json=[])
    if p == "/internal/registry/participants/import":
        return httpx.Response(200, json={"created": 1, "updated": 0, "errors": []})
    if p == "/internal/registry/results/import":
        return httpx.Response(
            200,
            json={
                "committed": body["commit"],
                "summary": {"total": 0, "errors": 0, "created": 0, "updated": 0, "unchanged": 0},
                "new_events": [],
                "lines": [],
            },  # fmt: skip
        )
    if p.startswith("/internal/registry/results/"):
        return httpx.Response(204)
    if p == "/internal/registry/results" and m == "PUT":
        return httpx.Response(200, json={"id": 7})
    return httpx.Response(404, json={"code": "not_found", "title": "нет"})


@pytest.fixture
def c(tmp_path):
    CALLS.clear()
    db = tmp_path / "c.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.fsp_client = ConnectorClient(
            "http://fspc", "tok", transport=httpx.MockTransport(_connector)
        )
        client.db_path = Path(db)
        yield client


def _user(c, email, role="candidate", consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def _admin(c):
    h = _user(c, "root@x.io", role="employer", consent=False)
    with sqlite3.connect(c.db_path) as con:
        con.execute("update users set role='fsp_admin' where email like 'root@%'")
    return h


def test_registry_link_sends_account_email_and_phone(c):
    h = _user(c, "jury-candidate@demo.fsp.test")
    patch = {"contacts": {"phone": "8 (900) 123-45-67"}}
    assert c.patch("/candidates/me/profile", json=patch, headers=h).status_code == 200
    r = c.post("/candidates/me/fsp/registry-link", headers=h)
    assert r.status_code == 200
    assert r.json() == {"linked": True, "matched_by": "email", "participant_id": "r-jury"}
    body = [x for x in CALLS if x[1] == "/internal/registry/match"][0][2]
    assert body["emails"] == ["jury-candidate@demo.fsp.test"]
    assert body["phones"] == ["8 (900) 123-45-67"]


def test_registry_link_miss_then_request(c):
    h = _user(c, "stranger@x.io")
    assert c.post("/candidates/me/fsp/registry-link", headers=h).json()["linked"] is False
    assert c.get("/candidates/me/fsp/request", headers=h).json() is None
    r = c.post(
        "/candidates/me/fsp/requests",
        json={"full_name": "Чужой Человек", "email": "other@x.ru", "event": "Кубок"},
        headers=h,
    )
    assert r.status_code == 201 and r.json()["status"] == "pending"
    sent = [x for x in CALLS if x[1] == "/internal/registry/requests"][0][2]
    assert sent["full_name"] == "Чужой Человек" and sent["candidate_id"]
    assert "candidate_id" not in r.json()  # кандидату свой ID не нужен
    assert (
        c.post("/candidates/me/fsp/requests", json={"full_name": "x"}, headers=h).status_code == 422
    )


def test_candidate_rights(c):
    assert c.post("/candidates/me/fsp/registry-link").status_code == 401
    e = _user(c, "e@x.io", role="employer")
    assert c.post("/candidates/me/fsp/registry-link", headers=e).status_code == 403
    assert c.get("/candidates/me/fsp/request", headers=e).status_code == 403
    nc = _user(c, "n@x.io", consent=False)
    assert c.post("/candidates/me/fsp/registry-link", headers=nc).status_code == 403


ADMIN_CALLS = [
    ("get", "/admin/fsp/events", None),
    ("post", "/admin/fsp/events",
     {"title": "Кубок", "discipline": "product", "level": "national", "date": "2026-05-01"}),
    ("get", "/admin/fsp/participants", None),
    ("post", "/admin/fsp/participants/import", {"csv": "ФИО,email\nА Б,a@b.ru"}),
    ("put", "/admin/fsp/results", {"participant_id": "r-1", "event_id": "e-1", "place": 1}),
    ("delete", "/admin/fsp/results/7", None),
    ("post", "/admin/fsp/registry/import", {"csv": "a;b;2026-01-01;1", "commit": False}),
    ("get", "/admin/fsp/requests", None),
    ("post", f"/admin/fsp/requests/{REQ_ID}/accept", {"participant_id": "r-1"}),
]  # fmt: skip


def test_admin_only_fsp_admin(c):
    cand = _user(c, "a@x.io")
    for method, path, body in ADMIN_CALLS:
        kw = {"json": body} if body is not None else {}
        assert getattr(c, method)(path, **kw).status_code == 401, path
        assert getattr(c, method)(path, headers=cand, **kw).status_code == 403, path
    assert not [x for x in CALLS if "/registry/" in x[1]]


def test_admin_flow(c):
    h = _admin(c)
    for method, path, body in ADMIN_CALLS:
        kw = {"json": body} if body is not None else {}
        r = getattr(c, method)(path, headers=h, **kw)
        assert r.status_code in (200, 201, 204), (path, r.text)
    acc = c.post(f"/admin/fsp/requests/{REQ_ID}/accept", json={"participant_id": "r-1"}, headers=h)
    assert acc.json()["status"] == "accepted"
    missing = c.post(f"/admin/fsp/requests/{uuid4()}/accept", json={"participant_id": "r-1"},
                     headers=h)  # fmt: skip
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    bad = c.post("/admin/fsp/events", json={"title": "К", "discipline": "x"}, headers=h)
    assert bad.status_code == 422
    q = c.get("/admin/fsp/participants", params={"q": "Иван"}, headers=h)
    assert q.status_code == 200
    assert [x for x in CALLS if x[1].endswith("/participants")][-1][3]["q"] == "Иван"


def test_registry_import_passes_options_to_connector(c):
    h = _admin(c)
    body = {"csv": "x;y;2026-01-01;1", "commit": True, "skip_errors": True, "create_events": ["k"]}
    r = c.post("/admin/fsp/registry/import", json=body, headers=h)
    assert r.status_code == 200 and r.json()["committed"] is True
    sent = [x for x in CALLS if x[1] == "/internal/registry/results/import"][-1][2]
    assert sent["skip_errors"] is True and sent["create_events"] == ["k"]
