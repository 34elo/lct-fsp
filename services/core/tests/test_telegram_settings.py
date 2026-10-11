"""ФСП, категория, статус и настройки из бота: /internal/tg/*."""

import json
import shutil
import sqlite3
from pathlib import Path

import fakeredis
import httpx
import pytest
from app.config import Settings
from app.fsp.client import ConnectorClient
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
SVC = {"Authorization": "Service bot-tok"}
TG, OTHER_TG, NO_CONSENT_TG = 888_001, 888_002, 888_003
CALLS: list[tuple[str, dict]] = []


def _connector(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else {}
    CALLS.append((request.url.path, body))
    if request.url.path == "/internal/links":
        if body["participant_id"] == "nobody":
            return httpx.Response(404, json={"code": "fsp_not_found", "title": "нет"})
        return httpx.Response(200, json={"method": "code", "masked_contact": "a***@x.ru"})
    if request.url.path == "/internal/links/verify":
        return httpx.Response(200, json={"verified": body["code"] == "123456"})
    return httpx.Response(404)


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("tpl") / "s.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    return db


def _hex(u):
    return str(u).replace("-", "")


@pytest.fixture
def c(tmp_path, template_db):
    CALLS.clear()
    db = tmp_path / "s.db"
    shutil.copy(template_db, db)
    app = build_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db}",
            ui_bus_enabled=False,
            service_token_bot="bot-tok",
        )
    )
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.fsp_client = ConnectorClient(
            "http://fspc", "tok", transport=httpx.MockTransport(_connector)
        )
        client.db = db
        yield client


def _db(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


def _candidate(c, email, tg, consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = r.json()["user"]["id"]
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    _db(
        c,
        "insert into telegram_accounts (user_id, tg_user_id, chat_id, linked_at)"
        " values (?,?,?,datetime('now'))",
        _hex(uid), tg, tg,
    )  # fmt: skip
    return h, uid


@pytest.fixture
def world(c):
    _candidate(c, "a@x.ru", TG)
    _candidate(c, "b@x.ru", OTHER_TG)
    return c


def test_requires_service_token(world):
    c = world
    assert c.get("/internal/tg/fsp", params={"tg_user_id": TG}).status_code == 401
    assert c.get("/internal/tg/category", params={"tg_user_id": TG}).status_code == 401
    assert c.get("/internal/tg/settings", params={"tg_user_id": TG}).status_code == 401
    assert (
        c.patch("/internal/tg/status", json={"tg_user_id": TG, "status": "dnd"}).status_code == 401
    )
    assert c.post("/internal/tg/fsp/sync", json={"tg_user_id": TG}).status_code == 401


def test_unknown_telegram_is_404(world):
    r = world.get("/internal/tg/settings", params={"tg_user_id": 1}, headers=SVC)
    assert r.status_code == 404 and r.json()["code"] == "telegram_unknown"


def test_status_and_settings_roundtrip(world):
    c = world
    s = c.get("/internal/tg/settings", params={"tg_user_id": TG}, headers=SVC).json()
    assert (
        s == {"salary_min": None, "formats": [], "search_status": "open"} or s["salary_min"] is None
    )
    r = c.patch("/internal/tg/status", json={"tg_user_id": TG, "status": "active"}, headers=SVC)
    assert r.status_code == 200 and r.json()["search_status"] == "active"
    r = c.patch(
        "/internal/tg/settings",
        json={"tg_user_id": TG, "salary_min": 230000, "formats": ["remote", "hybrid"]},
        headers=SVC,
    )
    assert r.status_code == 200
    assert r.json()["salary_min"] == 230000 and r.json()["formats"] == ["hybrid", "remote"]
    # частичный PATCH: форматы не трогаем, зарплату очищаем
    r = c.patch("/internal/tg/settings", json={"tg_user_id": TG, "salary_min": None}, headers=SVC)
    assert r.json()["salary_min"] is None and r.json()["formats"] == ["hybrid", "remote"]
    bad = c.patch("/internal/tg/status", json={"tg_user_id": TG, "status": "zzz"}, headers=SVC)
    assert bad.status_code == 422
    bad = c.patch("/internal/tg/settings", json={"tg_user_id": TG, "salary_min": -1}, headers=SVC)
    assert bad.status_code == 422
    # чужая анкета не меняется
    other = c.get("/internal/tg/settings", params={"tg_user_id": OTHER_TG}, headers=SVC).json()
    assert other["salary_min"] is None and other["formats"] == []


def test_writes_need_pd_consent(c):
    _candidate(c, "n@x.ru", NO_CONSENT_TG, consent=False)
    r = c.patch(
        "/internal/tg/status", json={"tg_user_id": NO_CONSENT_TG, "status": "dnd"}, headers=SVC
    )
    assert r.status_code == 403 and r.json()["code"] == "consent_required"
    r = c.post(
        "/internal/tg/fsp/link", json={"tg_user_id": NO_CONSENT_TG, "email": "a@b.ru"}, headers=SVC
    )
    assert r.status_code == 403 and CALLS == []


def test_fsp_link_verify_and_overview(world):
    c = world
    r = c.get("/internal/tg/fsp", params={"tg_user_id": TG}, headers=SVC)
    assert r.json()["linked"] is False and r.json()["achievements"] == []
    r = c.post("/internal/tg/fsp/link", json={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 422
    r = c.post(
        "/internal/tg/fsp/link", json={"tg_user_id": TG, "participant_id": "nobody"}, headers=SVC
    )
    assert r.status_code == 404 and r.json()["code"] == "fsp_not_found"
    r = c.post(
        "/internal/tg/fsp/link", json={"tg_user_id": TG, "participant_id": "p-anya"}, headers=SVC
    )
    assert r.status_code == 200 and r.json() == {"method": "code", "masked_contact": "a***@x.ru"}
    assert CALLS[-1][1]["manual"] is False
    r = c.post("/internal/tg/fsp/verify", json={"tg_user_id": TG, "code": "000000"}, headers=SVC)
    assert r.status_code == 200 and r.json() == {"verified": False}
    r = c.post("/internal/tg/fsp/verify", json={"tg_user_id": TG, "code": "123456"}, headers=SVC)
    assert r.json() == {"verified": True}


def test_fsp_sync_requires_link_and_is_rate_limited(world):
    c = world
    r = c.post("/internal/tg/fsp/sync", json={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 409 and r.json()["code"] == "fsp_not_linked"
    uid = _db(c, "select user_id from telegram_accounts where tg_user_id=?", TG)[0][0]
    _db(
        c,
        "insert into fsp_participants (candidate_id, participant_id, verified)"
        " values (?, 'p-anya', 1)",
        uid,
    )
    r = c.post("/internal/tg/fsp/sync", json={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 202
    r = c.post("/internal/tg/fsp/sync", json={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 429 and r.json()["code"] == "sync_too_often"
    ov = c.get("/internal/tg/fsp", params={"tg_user_id": TG}, headers=SVC).json()
    assert ov["linked"] is True and ov["participant_id"] == "p-anya"


def test_category_reads_grades_via_assessment_service(world):
    c = world
    assert c.get("/internal/tg/category", params={"tg_user_id": TG}, headers=SVC).json() == {
        "categories": [],
        "claims": [],
    }
    uid = _db(c, "select user_id from telegram_accounts where tg_user_id=?", TG)[0][0]
    _db(
        c,
        "insert into grades (candidate_id, profession, grade, theta, band_position, theta_by_type,"
        " integrity, needs_confirmation, low_confidence, source, confirmed_at, valid_until,"
        " next_change_at, updated_at) values (?, 'backend', 'middle', 0.2, 0.6, '{}', 1.0, 1, 0,"
        " 'seed', datetime('now'), datetime('now', '+300 days'), datetime('now'), datetime('now'))",
        uid,
    )
    r = c.get("/internal/tg/category", params={"tg_user_id": TG}, headers=SVC).json()
    assert [(x["profession"], x["grade"], x["needs_confirmation"]) for x in r["categories"]] == [
        ("backend", "middle", True)
    ]
    assert r["claims"] and r["claims"][0]["profession"] == "backend"
    assert r["claims"][0]["confirmed_grade"] == "middle"
    # чужие категории не видны
    other = c.get("/internal/tg/category", params={"tg_user_id": OTHER_TG}, headers=SVC).json()
    assert other["categories"] == []
