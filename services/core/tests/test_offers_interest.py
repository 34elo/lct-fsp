# ruff: noqa: F811
"""Интерес как первый шаг контакта: вилка, лимит, открыть / не интересно."""

import asyncio
import json
import uuid

import pytest
from app.notifications.handlers import register
from app.offers import router as offers_router
from app.offers import service
from fsp_contracts import Envelope
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.messaging import QUEUES, Consumer
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _events,
    _offer,
    _past,
    _vacancy,
    c,
    template_db,
)


def _interest(c, h, pid, **over):
    body = {"candidate_pseudo_id": pid, "salary_from": 200000, "salary_to": 260000,
            "message": "Нам интересен ваш опыт"} | over  # fmt: skip
    return c.post("/interests", json={k: v for k, v in body.items() if v is not None}, headers=h)


@pytest.fixture
def world(c):
    e = _employer(c, "e@x.ru")
    ch, pid, uid = _candidate(c, "c@x.ru", 1, salary_min=250000)
    return c, e, ch, pid, uid


def test_create_interest(world):
    c, e, ch, pid, uid = world
    r = _interest(c, e, pid)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "interest" and o["awaiting_reply_from"] == "candidate"
    assert (o["salary_from"], o["salary_to"]) == (200000, 260000)
    assert o["interest_at"] and o["invited_at"] is None
    assert o["candidate"]["pseudo_id"] == pid and o["contacts"] is None
    assert o["below_candidate_min"] is False
    assert _events(c) == ["offer.interest.sent"]
    (ver,) = _db(c, "select payload from outbox where type='offer.interest.sent'")[0]
    env = json.loads(ver)
    assert env["schema_version"] == 3 and env["payload"]["salary_to"] == 260000


def test_repeat_mark_is_idempotent(world):
    c, e, ch, pid, uid = world
    first = _interest(c, e, pid).json()
    r = _interest(c, e, pid, salary_from=210000)
    assert r.status_code == 201 and r.headers["Idempotent-Replay"] == "true"
    assert r.json()["id"] == first["id"] and r.json()["salary_from"] == 200000
    assert _db(c, "select count(*) from offers")[0][0] == 1
    assert _events(c) == ["offer.interest.sent"]


def test_salary_range_required_and_message_limit(world):
    c, e, ch, pid, uid = world
    for over in ({"salary_from": None}, {"salary_to": None}, {"salary_from": 0}):
        r = _interest(c, e, pid, **over)
        assert (r.status_code, r.json()["code"]) == (422, "salary_range_required"), over
    r = _interest(c, e, pid, salary_from=300000, salary_to=200000)
    assert (r.status_code, r.json()["code"]) == (422, "invalid_salary_range")
    assert _interest(c, e, pid, message="x" * 301).status_code == 422
    assert _interest(c, e, pid, message="x" * 300).status_code == 201


def test_weekly_limit_429(world, monkeypatch):
    c, e, ch, pid, uid = world
    monkeypatch.setattr(offers_router, "_LIMITS", service.OfferLimits(interest_company_per_week=2))
    pids = [_candidate(c, f"x{i}@x.ru", 10 + i)[1] for i in range(3)]
    assert _interest(c, e, pids[0]).status_code == 201
    assert _interest(c, e, pids[1]).status_code == 201
    r = _interest(c, e, pids[2])
    assert (r.status_code, r.json()["code"]) == (429, "interest_limit_exceeded")
    assert int(r.headers["Retry-After"]) > 0
    assert _interest(c, e, pids[0]).status_code == 201  # повтор отметки лимит не тратит
    _db(c, "update offers set interest_at=?, created_at=?", _past(days=8), _past(days=8))
    assert _interest(c, e, pids[2]).status_code == 201  # окно скользит


def test_interests_do_not_eat_daily_offer_limit(world, monkeypatch):
    c, e, ch, pid, uid = world
    monkeypatch.setattr(offers_router, "_LIMITS", service.OfferLimits(company_per_day=1))
    assert _interest(c, e, pid).status_code == 201
    _, pid2, _ = _candidate(c, "c2@x.ru", 2)
    assert _offer(c, e, _vacancy(c, e), pid2).status_code == 201


def test_candidate_sees_aggregate_without_contacts(world):
    c, e, ch, pid, uid = world
    e2 = _employer(c, "e2@x.ru", name="Beta", inn="500100732259")
    _interest(c, e, pid)
    _interest(c, e2, pid, salary_from=230000, salary_to=300000)
    r = c.get("/candidates/me/interests", headers=ch)
    assert r.status_code == 200
    s = r.json()
    assert (s["companies"], s["salary_from_min"], s["salary_to_max"]) == (2, 200000, 300000)
    assert {i["company"]["name"] for i in s["items"]} == {"Acme Labs", "Beta"}
    assert all(i["status"] == "interest" for i in s["items"])
    blob = json.dumps(s, ensure_ascii=False)
    for leak in ("e@x.ru", "e2@x.ru", "phone", 'contacts": {'):
        assert leak not in blob
    # интересы без приглашения не попадают в список офферов
    assert c.get("/candidates/me/offers", headers=ch).json() == []


def test_open_then_invite_then_accept(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    # до «открыть» приглашать нельзя, контакты закрыты
    r = c.post(f"/interests/{iid}/invite", json={"title": "Backend"}, headers=e)
    assert (r.status_code, r.json()["code"]) == (409, "interest_not_opened")
    assert c.get(f"/offers/{iid}/contacts", headers=e).status_code == 409
    r = c.post(f"/interests/{iid}/open", headers=ch)
    assert r.status_code == 200 and r.json()["status"] == "interest_opened"
    assert r.json()["awaiting_reply_from"] == "company"
    again = c.post(f"/interests/{iid}/open", headers=ch)  # повтор — без изменений
    assert again.status_code == 200 and again.json()["status"] == "interest_opened"
    assert c.get(f"/offers/{iid}/contacts", headers=e).status_code == 409  # анонимность
    # без вакансии нужен title
    r = c.post(f"/interests/{iid}/invite", headers=e)
    assert (r.status_code, r.json()["code"]) == (422, "title_required")
    body = {"title": "Backend", "salary_to": 280000, "contact_method": "telegram"}
    r = c.post(f"/interests/{iid}/invite", json=body, headers=e)
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["status"] == "sent" and o["invited_at"] and o["salary_to"] == 280000
    assert c.post(f"/interests/{iid}/invite", json=body, headers=e).json()["status"] == "sent"
    assert _events(c) == ["offer.interest.sent", "offer.interest.opened", "offer.sent"]
    assert [x["id"] for x in c.get("/candidates/me/offers", headers=ch).json()] == [iid]
    assert c.get("/candidates/me/interests", headers=ch).json()["companies"] == 0
    assert c.post(f"/offers/{iid}/accept", headers=ch).json()["status"] == "accepted"
    assert c.get(f"/offers/{iid}/contacts", headers=e).status_code == 200


def test_cannot_accept_interest_directly(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    r = c.post(f"/offers/{iid}/accept", headers=ch)
    assert (r.status_code, r.json()["code"]) == (409, "invalid_transition")
    r = c.post(f"/offers/{iid}/messages", json={"text": "привет"}, headers=e)
    assert r.status_code == 409  # переписки до приглашения нет


def test_decline_with_reason_idempotent(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    r = c.post(f"/interests/{iid}/decline", json={"reason": "wrong_company"}, headers=ch)
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert r.json()["decline"]["reason"] == "wrong_company"
    again = c.post(f"/interests/{iid}/decline", json={"reason": "wrong_company"}, headers=ch)
    assert again.status_code == 200
    other = c.post(f"/interests/{iid}/decline", json={"reason": "low_salary"}, headers=ch)
    assert other.status_code == 409
    assert c.post(f"/interests/{iid}/open", headers=ch).status_code == 409
    bad = c.post(f"/interests/{iid}/decline", json={"reason": "nope"}, headers=ch)
    assert bad.status_code == 422
    assert _events(c) == ["offer.interest.sent", "offer.interest.declined"]
    # после отказа можно снова отметить интерес (новая строка)
    assert _interest(c, e, pid).json()["id"] != iid


def test_withdraw_interest(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    assert c.post(f"/offers/{iid}/withdraw", headers=e).json()["status"] == "withdrawn"
    assert _events(c)[-1] == "offer.interest.withdrawn"


def test_foreign_interest_is_404(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    e2 = _employer(c, "e2@x.ru", name="Other", inn="500100732259")
    ch2, _, _ = _candidate(c, "c2@x.ru", 2)
    ghost = str(uuid.uuid4())
    for h, path in (
        (ch2, f"/interests/{iid}/open"), (ch, f"/interests/{ghost}/open"),
        (e2, f"/interests/{iid}/invite"), (e, f"/interests/{ghost}/invite"),
    ):  # fmt: skip
        r = c.post(path, headers=h)
        assert (r.status_code, r.json()["code"]) == (404, "interest_not_found"), path
    r = c.post(f"/interests/{iid}/decline", json={"reason": "other"}, headers=ch2)
    assert r.status_code == 404
    assert c.get("/candidates/me/interests", headers=ch2).json()["companies"] == 0
    # обычный оффер — не интерес
    vid = _vacancy(c, e)
    oid = _offer(c, e, vid, pid).json()["id"]
    assert c.post(f"/interests/{oid}/open", headers=ch).status_code == 404
    # роли
    assert c.post("/interests", json={"candidate_pseudo_id": pid}, headers=ch).status_code == 403
    assert c.get("/candidates/me/interests", headers=e).status_code == 403
    assert c.post(f"/interests/{iid}/open", headers=e).status_code == 403
    assert c.get("/candidates/me/interests").status_code == 401


def test_unknown_candidate_and_unverified_company(world):
    c, e, ch, pid, uid = world
    r = _interest(c, e, "nope")
    assert (r.status_code, r.json()["code"]) == (404, "candidate_not_found")
    e3 = _employer(c, "e3@x.ru", name="Gamma", inn="500100732259", verified=False)
    assert _interest(c, e3, pid).status_code == 403


def test_open_offer_blocks_interest(world):
    c, e, ch, pid, uid = world
    vid = _vacancy(c, e)
    _offer(c, e, vid, pid)
    r = _interest(c, e, pid)
    assert (r.status_code, r.json()["code"]) == (409, "offer_exists")


def _expire(c) -> int:
    async def run() -> int:
        engine = make_engine(f"sqlite+aiosqlite:///{c.db}")
        try:
            total = 0
            for _ in range(2):
                async with make_session_factory(engine)() as s:
                    total = total * 10 + await service.expire_due(s)
                    await s.commit()
            return total
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_expires_by_cron(world):
    c, e, ch, pid, uid = world
    i1 = _interest(c, e, pid).json()["id"]
    _, pid2, _ = _candidate(c, "c2@x.ru", 2)
    i2 = _interest(c, e, pid2).json()["id"]
    # второй интерес кандидат уже открыл — истекает тоже
    _db(c, "update offers set status='interest_opened' where id=?", i2.replace("-", ""))
    _db(c, "update offers set expires_at=?", _past(minutes=1))
    r = c.post(f"/interests/{i1}/open", headers=ch)
    assert (r.status_code, r.json()["code"]) == (409, "offer_expired")
    assert _expire(c) == 20  # второй прогон ничего не меняет
    for oid in (i1, i2):
        (st,) = _db(c, "select status from offers where id=?", oid.replace("-", ""))[0]
        assert st == "expired"
    assert _events(c, "offer.interest.expired") == ["offer.interest.expired"] * 2


def test_interest_notifications(world):
    c, e, ch, pid, uid = world
    iid = _interest(c, e, pid).json()["id"]
    c.post(f"/interests/{iid}/open", headers=ch)
    url = f"sqlite+aiosqlite:///{c.db}"
    ui = []

    async def run():
        engine = make_engine(url)
        consumers = {"core.handlers": Consumer(QUEUES["core.handlers"])}

        async def publish(msg):
            ui.append(msg)

        register(consumers, make_session_factory(engine), publish)
        rows = _db(c, "select payload from outbox where type like 'offer.interest.%' order by id")
        try:
            for (payload,) in rows:
                env = Envelope.model_validate(json.loads(payload))
                for _ in range(2):  # повторная доставка не дублирует
                    await consumers["core.handlers"].dispatch(env)
        finally:
            await engine.dispose()

    asyncio.run(run())
    types = [t for (t,) in _db(c, "select type from notifications order by rowid")]
    assert types == ["interest_new", "interest_opened"]
    blob = json.dumps([json.loads(p) for (p,) in _db(c, "select payload from notifications")])
    for pii in ("c@x.ru", pid):
        assert pii not in blob
