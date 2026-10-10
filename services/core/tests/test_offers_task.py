# ruff: noqa: F811
"""Задача в приглашении (E33-3): доставка, срок, идемпотентный ответ, видимость результата."""

import uuid

import pytest
from app.offers import invite_task
from app.offers.invite_task import TaskInfo
from fsp_platform.app import ProblemError
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _offer,
    _past,
    _vacancy,
    c,
    template_db,
)
from test_offers_interest import _interest

FAMILY = uuid.uuid4()
LONG = uuid.uuid4()


class FakeBank:
    """Порт банка блока 1: два семейства; ответ «42» верный."""

    def __init__(self):
        self.submits = []

    async def describe(self, session, family_id, *, company_id, user_id):
        if family_id == FAMILY:
            return TaskInfo(title="Найди баг", kind="find_bug", minutes=10)
        if family_id == LONG:
            return TaskInfo(title="Большая", kind="code", minutes=45)
        raise ProblemError(404, "not_found", "Задание не найдено")

    async def item(self, session, family_id, *, candidate_id, offer_id):
        return {"kind": "find_bug", "stem": f"вариант {offer_id}"}

    async def submit(self, session, family_id, *, candidate_id, offer_id, answer):
        self.submits.append((candidate_id, offer_id, answer))
        return 1.0 if answer == 42 else 0.0


@pytest.fixture
def bank():
    b = FakeBank()
    old = invite_task.get_bank()
    invite_task.set_bank(b)
    yield b
    invite_task.set_bank(old)


@pytest.fixture
def world(c, bank):
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    ch, pid, uid = _candidate(c, "c@x.ru", 1)
    return c, e, vid, ch, pid, uid


def _task(**over):
    return {"family_id": str(FAMILY), "deadline_days": 3} | over


def test_task_delivered_and_answer_idempotent(world, bank):
    c, e, vid, ch, pid, uid = world
    r = _offer(c, e, vid, pid, task=_task())
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["task"]["title"] == "Найди баг" and o["task"]["minutes"] == 10
    assert o["task"]["answered_at"] is None and o["task"]["answer"] is None

    v = c.get(f"/offers/{o['id']}/task", headers=ch)
    assert v.status_code == 200, v.text
    assert v.json()["can_answer"] is True and o["id"] in v.json()["item"]["stem"]
    assert "correct" not in str(v.json()) and "key" not in str(v.json())

    a = c.post(f"/offers/{o['id']}/task/answer", json={"answer": 42}, headers=ch)
    assert a.status_code == 200 and a.json()["score"] == 1.0
    again = c.post(f"/offers/{o['id']}/task/answer", json={"answer": 7}, headers=ch)
    assert again.status_code == 200 and again.headers["Idempotent-Replay"] == "true"
    assert again.json()["score"] == 1.0
    assert again.json()["answered_at"].rstrip("Z") == a.json()["answered_at"].rstrip("Z")
    assert len(bank.submits) == 1  # доказательство в профиль пишется один раз

    after = c.get(f"/offers/{o['id']}/task", headers=ch).json()
    assert after["can_answer"] is False and after["item"] is None
    mine = c.get("/candidates/me/offers", headers=ch).json()[0]
    assert mine["task"]["score"] == 1.0

    full = c.get(f"/offers/{o['id']}", headers=e).json()
    assert full["task"]["score"] == 1.0 and full["task"]["answer"] == 42
    assert full["task"]["family_id"] == str(FAMILY)


def test_result_not_visible_to_other_companies(world, bank):
    c, e, vid, ch, pid, uid = world
    o = _offer(c, e, vid, pid, task=_task()).json()
    c.post(f"/offers/{o['id']}/task/answer", json={"answer": 42}, headers=ch)
    e2 = _employer(c, "e2@x.ru", name="Beta", inn="500100732259")
    assert c.get(f"/offers/{o['id']}", headers=e2).status_code == 404
    assert o["id"] not in {x["id"] for x in c.get("/offers", headers=e2).json()}
    o2 = _offer(c, e2, _vacancy(c, e2), pid).json()  # другая компания приглашает без задачи
    assert o2["task"] is None
    assert c.get(f"/offers/{o2['id']}/task", headers=ch).status_code == 404
    other_ch, _, _ = _candidate(c, "c9@x.ru", 9)
    assert c.get(f"/offers/{o['id']}/task", headers=other_ch).status_code == 404
    r = c.post(f"/offers/{o['id']}/task/answer", json={"answer": 1}, headers=other_ch)
    assert r.status_code == 404
    assert c.get(f"/offers/{o['id']}/task", headers=e).status_code == 403


def test_accept_without_solving(world, bank):
    c, e, vid, ch, pid, uid = world
    o = _offer(c, e, vid, pid, task=_task()).json()
    assert c.post(f"/offers/{o['id']}/accept", headers=ch).status_code == 200
    assert bank.submits == []
    assert c.get(f"/offers/{o['id']}", headers=e).json()["task"]["answered_at"] is None


def test_task_checks_before_offer(world, bank):
    c, e, vid, ch, pid, uid = world
    r = _offer(c, e, vid, pid, task=_task(family_id=str(LONG)))
    assert (r.status_code, r.json()["code"]) == (422, "task_too_long")
    r = _offer(c, e, vid, pid, task=_task(family_id=str(uuid.uuid4())))
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert _offer(c, e, vid, pid, task=_task(deadline_days=15)).status_code == 422
    assert _db(c, "select count(*) from offers") == [(0,)]


def test_deadline_passed(world, bank):
    c, e, vid, ch, pid, uid = world
    o = _offer(c, e, vid, pid, task=_task()).json()
    _db(c, "update offer_tasks set deadline_at=?", _past(hours=1))
    v = c.get(f"/offers/{o['id']}/task", headers=ch).json()
    assert v["can_answer"] is False and v["item"] is None
    r = c.post(f"/offers/{o['id']}/task/answer", json={"answer": 42}, headers=ch)
    assert (r.status_code, r.json()["code"]) == (409, "task_deadline_passed")
    assert bank.submits == []


def test_closed_offer_rejects_answer(world, bank):
    c, e, vid, ch, pid, uid = world
    o = _offer(c, e, vid, pid, task=_task()).json()
    assert c.post(f"/offers/{o['id']}/decline", json={"reason": "other"}, headers=ch).status_code
    r = c.post(f"/offers/{o['id']}/task/answer", json={"answer": 42}, headers=ch)
    assert (r.status_code, r.json()["code"]) == (409, "offer_closed")


def test_task_in_invitation_from_interest(world, bank):
    c, e, vid, ch, pid, uid = world
    o = _interest(c, e, pid).json()
    assert c.post(f"/interests/{o['id']}/open", headers=ch).status_code == 200
    assert c.get(f"/offers/{o['id']}/task", headers=ch).status_code == 404
    r = c.post(
        f"/interests/{o['id']}/invite", json={"title": "Backend", "task": _task()}, headers=e
    )
    assert r.status_code == 200, r.text
    assert r.json()["task"]["title"] == "Найди баг"
    again = c.post(f"/interests/{o['id']}/invite", json={"task": _task()}, headers=e)
    assert again.status_code == 200
    assert _db(c, "select count(*) from offer_tasks") == [(1,)]
    assert c.get(f"/offers/{o['id']}/task", headers=ch).json()["can_answer"] is True


def test_bank_unavailable_does_not_break_offer_without_task(c, monkeypatch):
    from app.assessment import service as assessment

    monkeypatch.delattr(assessment, "invite_task_describe")  # банк Б1 «ещё не отдал» функции
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    ch, pid, uid = _candidate(c, "c@x.ru", 1)
    assert _offer(c, e, vid, pid).status_code == 201  # без задачи порт не нужен
    _, pid2, _ = _candidate(c, "c2@x.ru", 2)
    r = _offer(c, e, vid, pid2, task=_task())
    assert (r.status_code, r.json()["code"]) == (503, "task_bank_unavailable")
    assert _db(c, "select count(*) from offers") == [(1,)]
