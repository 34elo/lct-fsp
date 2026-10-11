"""Офферы из бота: /internal/tg/offers*."""

import shutil
import sqlite3
import uuid
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
SVC = {"Authorization": "Service bot-tok"}
TG = 777_001
OTHER_TG = 777_002


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("tpl") / "o.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    with sqlite3.connect(db) as con:
        con.execute(
            "insert into skills (id, slug, name, kind, status, source, support_candidates,"
            " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
            (uuid.uuid4().hex, "python", "python", "tech", "active", "seed"),
        )
    return db


@pytest.fixture
def c(tmp_path, template_db):
    db = tmp_path / "o.db"
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
        client.db = db
        yield client


def _db(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


def _hex(u):
    return str(u).replace("-", "")


def _auth(c, email, role):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


@pytest.fixture
def world(c):
    e, _ = _auth(c, "e@x.ru", "employer")
    co = c.post("/companies", json={"name": "Acme Labs", "inn": INN}, headers=e).json()
    _db(c, "update companies set status='verified' where id=?", _hex(co["id"]))
    body = {
        "title": "Backend", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python"}],
    }  # fmt: skip
    vid = c.post("/vacancies", json=body, headers=e).json()["id"]
    assert c.post(f"/vacancies/{vid}/publish", headers=e).status_code == 200
    ch, ch_uid = _auth(c, "c@x.ru", "candidate")
    grants = [{"type": "pd_processing", "granted": True}]
    assert c.put("/me/consents", json={"consents": grants}, headers=ch).status_code == 200
    assert c.get("/candidates/me/profile", headers=ch).status_code == 200
    _db(c, "update candidates set primary_role='backend', grade='middle', pseudo_id='pid0001'")
    for uid, tg in ((ch_uid, TG),):
        _db(
            c,
            "insert into telegram_accounts (user_id, tg_user_id, chat_id, linked_at)"
            " values (?,?,?,datetime('now'))",
            _hex(uid), tg, tg,
        )  # fmt: skip
    other, other_uid = _auth(c, "c2@x.ru", "candidate")
    _db(
        c,
        "insert into telegram_accounts (user_id, tg_user_id, chat_id, linked_at)"
        " values (?,?,?,datetime('now'))",
        _hex(other_uid), OTHER_TG, OTHER_TG,
    )  # fmt: skip
    return c, e, vid


def _offer(c, e, vid):
    body = {"vacancy_id": vid, "candidate_pseudo_id": "pid0001", "salary_from": 250000,
            "salary_to": 320000, "message": "Привет!"}  # fmt: skip
    r = c.post("/offers", json=body, headers={**e, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _status(c, oid):
    return _db(c, "select status from offers where id=?", _hex(oid))[0][0]


def test_requires_service_token(world):
    c, e, vid = world
    oid = _offer(c, e, vid)
    assert c.get("/internal/tg/offers", params={"tg_user_id": TG}).status_code == 401
    r = c.post(f"/internal/tg/offers/{oid}/view", json={"tg_user_id": TG})
    assert r.status_code == 401


def test_list_and_view_marks_viewed(world):
    c, e, vid = world
    oid = _offer(c, e, vid)
    r = c.get("/internal/tg/offers", params={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 200 and [o["offer_id"] for o in r.json()] == [oid]
    assert r.json()[0]["company_name"] == "Acme Labs" and r.json()[0]["status"] == "sent"
    assert _status(c, oid) == "sent"
    v = c.post(f"/internal/tg/offers/{oid}/view", json={"tg_user_id": TG}, headers=SVC)
    assert v.status_code == 200 and v.json()["status"] == "viewed"
    assert (v.json()["salary_from"], v.json()["salary_to"]) == (250000, 320000)
    assert v.json()["vacancy_title"] == "Backend" and v.json()["formats"] == ["remote"]
    again = c.post(f"/internal/tg/offers/{oid}/view", json={"tg_user_id": TG}, headers=SVC)
    assert again.status_code == 200 and again.json()["status"] == "viewed"


def test_foreign_offer_is_404(world):
    c, e, vid = world
    oid = _offer(c, e, vid)
    for path, body in (
        ("view", {}),
        ("accept", {}),
        ("decline", {"reason": "other"}),
    ):
        r = c.post(
            f"/internal/tg/offers/{oid}/{path}", json={"tg_user_id": OTHER_TG, **body}, headers=SVC
        )
        assert r.status_code == 404 and r.json()["code"] == "offer_not_found", path
    assert c.get("/internal/tg/offers", params={"tg_user_id": OTHER_TG}, headers=SVC).json() == []
    unknown = c.post(f"/internal/tg/offers/{oid}/view", json={"tg_user_id": 1}, headers=SVC)
    assert unknown.status_code == 404 and unknown.json()["code"] == "telegram_unknown"
    assert _status(c, oid) == "sent"


def test_accept_then_repeat_conflicts(world):
    c, e, vid = world
    oid = _offer(c, e, vid)
    r = c.post(f"/internal/tg/offers/{oid}/accept", json={"tg_user_id": TG}, headers=SVC)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert _db(c, "select count(*) from contact_reveals")[0][0] == 1
    again = c.post(f"/internal/tg/offers/{oid}/accept", json={"tg_user_id": TG}, headers=SVC)
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"
    # принятый оффер остаётся в списке
    assert len(c.get("/internal/tg/offers", params={"tg_user_id": TG}, headers=SVC).json()) == 1


def test_decline_with_reason(world):
    c, e, vid = world
    oid = _offer(c, e, vid)
    bad = c.post(
        f"/internal/tg/offers/{oid}/decline", json={"tg_user_id": TG, "reason": "zzz"}, headers=SVC
    )
    assert bad.status_code == 422
    r = c.post(
        f"/internal/tg/offers/{oid}/decline",
        json={"tg_user_id": TG, "reason": "low_salary"},
        headers=SVC,
    )
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert _db(c, "select decline_reason from offers where id=?", _hex(oid)) == [("low_salary",)]
    # отклонённого нет в списке активных
    assert c.get("/internal/tg/offers", params={"tg_user_id": TG}, headers=SVC).json() == []
