"""Уведомления: offer.* и skills.profile.updated → БД, ui.user.*, notify.telegram (E8-3)."""

import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from app.notifications.handlers import register
from fastapi.testclient import TestClient
from fsp_contracts import Envelope, new_envelope
from fsp_contracts.events import ProfileDiff, SkillLevelChange, SkillsProfileUpdated
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
CHAT = 424242


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("tpl") / "n.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    with sqlite3.connect(db) as con:
        con.execute(
            "insert into skills (id, slug, name, kind, status, source, support_candidates,"
            " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
            (uuid.uuid4().hex, "python", "python", "tech", "active", "seed"),
        )
    return db


@pytest.fixture
def c(tmp_path, template_db):
    db = tmp_path / "n.db"
    shutil.copy(template_db, db)
    url = f"sqlite+aiosqlite:///{db}"
    app = build_app(Settings(database_url=url, ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db = db
        client.factory = make_session_factory(make_engine(url))
        client.ui = []
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
    e, e_uid = _auth(c, "e@x.ru", "employer")
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
    return c, e, e_uid, vid, ch, ch_uid


def _link_tg(c, headers, uid, consent=True):
    _db(
        c,
        "insert into telegram_accounts (user_id, tg_user_id, chat_id, linked_at)"
        " values (?,?,?,datetime('now'))",
        _hex(uid), hash(uid) % 10**9, CHAT,
    )  # fmt: skip
    if consent:
        body = {"consents": [{"type": "telegram_notifications", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=headers).status_code == 200


def _offer(c, e, vid):
    body = {"vacancy_id": vid, "candidate_pseudo_id": "pid0001", "salary_from": 250000,
            "salary_to": 320000, "message": "Привет!"}  # fmt: skip
    r = c.post("/offers", json=body, headers={**e, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _drain(c, types=("offer.%", "skills.profile.updated"), repeat=1):
    """Доставляем события из outbox в core.handlers (как это делает relay + брокер)."""
    consumers = {"core.handlers": Consumer(QUEUES["core.handlers"])}

    async def publish(msg):
        c.ui.append(msg)

    register(consumers, c.factory, publish)
    rows = []
    for t in types:
        rows += _db(c, "select id, payload from outbox where type like ? order by id", t)
    for _, payload in sorted(rows):
        env = Envelope.model_validate(json.loads(payload))
        for _ in range(repeat):
            asyncio.run(consumers["core.handlers"].dispatch(env))


def _tg(c):
    return [
        json.loads(r[0])["payload"]
        for r in _db(c, "select payload from outbox where type='notify.telegram' order by id")
    ]


def _notes(c):
    return _db(c, "select user_id, type, channels from notifications order by rowid")


def test_offer_sent_notifies_candidate_with_buttons(world):
    c, e, e_uid, vid, ch, ch_uid = world
    _link_tg(c, ch, ch_uid)
    oid = _offer(c, e, vid)
    _drain(c)
    assert [n[1] for n in _notes(c)] == ["offer_new"]
    assert json.loads(_notes(c)[0][2]) == ["web", "tg"]
    (cmd,) = _tg(c)
    assert cmd["chat_id"] == CHAT and cmd["template"] == "offer_new"
    assert cmd["edit_of"] == f"offer:{oid}"
    d = cmd["data"]
    assert d["company_name"] == "Acme Labs" and (d["salary_from"], d["salary_to"]) == (
        250000,
        320000,
    )
    assert d["vacancy_title"] == "Backend"
    cbs = [b["callback_data"] for row in cmd["buttons"] for b in row]
    assert cbs == [f"o:{a}:{oid}" for a in "adqv"]
    assert all(len(x.encode()) <= 64 for x in cbs)
    events = [(m.user_id, m.event) for m in c.ui]
    assert (uuid.UUID(ch_uid), "offer.created") in events
    assert (uuid.UUID(ch_uid), "notification.new") in events


def test_no_telegram_without_link(world):
    c, e, e_uid, vid, ch, ch_uid = world
    _offer(c, e, vid)
    _drain(c)  # чата нет
    assert _tg(c) == [] and json.loads(_notes(c)[0][2]) == ["web"]


def test_telegram_requires_consent(world):
    c, e, e_uid, vid, ch, ch_uid = world
    _link_tg(c, ch, ch_uid, consent=False)  # чат привязан, согласия нет
    _offer(c, e, vid)
    _drain(c)
    assert _tg(c) == [] and json.loads(_notes(c)[0][2]) == ["web"]


def test_redelivery_is_idempotent(world):
    c, e, e_uid, vid, ch, ch_uid = world
    _link_tg(c, ch, ch_uid)
    _offer(c, e, vid)
    _drain(c, repeat=3)
    assert len(_notes(c)) == 1 and len(_tg(c)) == 1
    assert len([m for m in c.ui if m.event == "notification.new"]) == 1


def test_accept_notifies_company_without_candidate_pii(world):
    c, e, e_uid, vid, ch, ch_uid = world
    _link_tg(c, e, e_uid)
    oid = _offer(c, e, vid)
    assert c.post(f"/offers/{oid}/accept", headers=ch).status_code == 200
    _drain(c)
    types = [(str(n[0]), n[1]) for n in _notes(c)]
    assert (_hex(e_uid), "offer_accepted") in types
    (cmd,) = _tg(c)
    assert cmd["template"] == "offer_updated"
    blob = json.dumps(cmd, ensure_ascii=False) + json.dumps(
        [json.loads(r[0]) for r in _db(c, "select payload from notifications")], ensure_ascii=False
    )
    for pii in ("c@x.ru", "pid0001", ch_uid):
        assert pii not in blob
    assert any(m.event == "offer.updated" and m.user_id == uuid.UUID(e_uid) for m in c.ui)


def test_decline_reason_goes_to_company(world):
    c, e, e_uid, vid, ch, ch_uid = world
    oid = _offer(c, e, vid)
    r = c.post(f"/offers/{oid}/decline", json={"reason": "low_salary"}, headers=ch)
    assert r.status_code == 200
    _drain(c)
    row = _db(c, "select type, payload from notifications where type='offer_declined'")
    assert len(row) == 1 and json.loads(row[0][1])["decline_reason"] == "low_salary"


def test_message_goes_to_other_side_without_text(world):
    c, e, e_uid, vid, ch, ch_uid = world
    oid = _offer(c, e, vid)
    c.post(f"/offers/{oid}/accept", headers=ch)
    r = c.post(f"/offers/{oid}/messages", json={"text": "секретный текст"}, headers=ch)
    assert r.status_code in (200, 201), r.text
    _drain(c)
    rows = _db(c, "select user_id, payload from notifications where type='offer_message'")
    assert [r[0] for r in rows] == [_hex(e_uid)]
    assert "секретный текст" not in json.dumps(rows, ensure_ascii=False)


def test_company_status_change_notifies_candidate(world):
    c, e, e_uid, vid, ch, ch_uid = world
    oid = _offer(c, e, vid)
    c.post(f"/offers/{oid}/accept", headers=ch)
    assert (
        c.post(f"/offers/{oid}/status", json={"status": "interview"}, headers=e).status_code == 200
    )
    _drain(c)
    rows = _db(c, "select user_id from notifications where type='offer_status'")
    assert [r[0] for r in rows] == [_hex(ch_uid)]


def test_profile_updated_only_on_significant_diff(world):
    c, e, e_uid, vid, ch, ch_uid = world
    uid = uuid.UUID(ch_uid)
    consumers = {"core.handlers": Consumer(QUEUES["core.handlers"])}
    register(consumers, c.factory, None)

    def send(diff):
        env = new_envelope(
            "skills.profile.updated", "core",
            SkillsProfileUpdated(candidate_id=uid, profile_version=2, diff=diff),
        )  # fmt: skip
        asyncio.run(consumers["core.handlers"].dispatch(env))

    send(ProfileDiff())
    assert _notes(c) == []
    send(ProfileDiff(skills_up=[SkillLevelChange(slug="python", **{"from": 2}, to=3)]))
    assert [n[1] for n in _notes(c)] == ["profile_updated"]
