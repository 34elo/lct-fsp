# ruff: noqa: F811
"""Лента активности работодателя (E35-12b): события, права, приватность."""

import uuid

import pytest
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _offer,
    _vacancy,
    c,
    template_db,
)
from test_offers_interest import _interest


def _hex(s: str) -> str:
    return s.replace("-", "")


def _kinds(c, h):
    r = c.get("/employer/activity", headers=h)
    assert r.status_code == 200, r.text
    return [(i["kind"], i["candidate"]["pseudo_id"]) for i in r.json()["items"]]


@pytest.fixture
def world(c):
    e = _employer(c, "e@x.ru")
    ch, pid, uid = _candidate(c, "c@x.ru", 1, salary_min=250000)
    return c, e, ch, pid, uid


def test_empty_and_roles(c):
    e = _employer(c, "e@x.ru")
    assert c.get("/employer/activity", headers=e).json() == {"items": []}
    assert c.get("/employer/activity").status_code == 401
    ch, _, _ = _candidate(c, "c@x.ru", 1)
    assert c.get("/employer/activity", headers=ch).status_code == 403


def test_interest_opened_and_declined(world):
    c, e, ch, pid, uid = world
    o = _interest(c, e, pid).json()
    assert _kinds(c, e) == []  # пока кандидат не ответил
    assert c.post(f"/interests/{o['id']}/open", headers=ch).status_code == 200
    items = c.get("/employer/activity", headers=e).json()["items"]
    assert [i["kind"] for i in items] == ["interest_opened"]
    it = items[0]
    assert it["link"] == f"/employer/offers/{o['id']}" and it["offer_id"] == o["id"]
    assert set(it["candidate"]) == {"pseudo_id", "pseudonym", "primary_role", "grade"}

    ch2, pid2, _ = _candidate(c, "c2@x.ru", 2)
    o2 = _interest(c, e, pid2).json()
    r = c.post(f"/interests/{o2['id']}/decline", json={"reason": "low_salary"}, headers=ch2)
    assert r.status_code == 200, r.text
    got = c.get("/employer/activity", headers=e).json()["items"]
    assert {i["kind"] for i in got} == {"interest_opened", "interest_declined"}
    declined = next(i for i in got if i["kind"] == "interest_declined")
    assert declined["detail"] == "low_salary"


def test_invitation_accepted_and_task_answer(world):
    c, e, ch, pid, uid = world
    vid = _vacancy(c, e)
    o = _offer(c, e, vid, pid).json()
    assert c.post(f"/offers/{o['id']}/accept", headers=ch).status_code == 200
    (cid,) = _db(c, "select company_id from offers where id=?", _hex(o["id"]))[0]
    _db(
        c,
        "insert into offer_tasks (offer_id, company_id, family_id, title, kind, minutes,"
        " deadline_at, answered_at, created_at) values (?,?,?,?,?,?,datetime('now'),"
        " datetime('now'),datetime('now'))",
        _hex(o["id"]), cid, _hex(str(uuid.uuid4())), "Тестовое", "code", 30,
    )  # fmt: skip
    kinds = {k for k, _ in _kinds(c, e)}
    assert kinds == {"invitation_accepted", "task_answered"}
    body = c.get("/employer/activity", headers=e).json()
    # приватность: ни контактов, ни ПДн в ленте
    text = str(body)
    assert "contacts" not in text and "email" not in text and "c@x.ru" not in text


def test_foreign_company_sees_nothing(world):
    c, e, ch, pid, uid = world
    o = _interest(c, e, pid).json()
    c.post(f"/interests/{o['id']}/open", headers=ch)
    other = _employer(c, "e2@x.ru", name="Other", inn="7707083893")
    assert _kinds(c, other) == []
    assert len(_kinds(c, e)) == 1


def test_subscription_hit_respects_visibility(world):
    c, e, ch, pid, uid = world
    (cid,) = _db(c, "select id from companies")[0]
    sid = str(uuid.uuid4())
    _db(
        c,
        "insert into category_subscriptions (id, company_id, profession, grades, skills, formats,"
        " only_confirmed, created_at) values (?,?,?,?,?,?,0,datetime('now'))",
        _hex(sid), cid, "backend", "[]", "[]", "[]",
    )  # fmt: skip
    _db(
        c,
        "insert into category_subscription_hits (subscription_id, candidate_id, created_at)"
        " values (?,?,datetime('now'))",
        _hex(sid), uid,
    )  # fmt: skip
    items = c.get("/employer/activity", headers=e).json()["items"]
    assert [(i["kind"], i["subscription_id"], i["detail"]) for i in items] == [
        ("subscription_hit", sid, "backend")
    ]
    assert items[0]["link"] == f"/employer/candidates/{pid}"
    other = _employer(c, "e2@x.ru", name="Other", inn="7707083893")
    assert _kinds(c, other) == []
    # кандидат ушёл из публикации — попадание из ленты исчезает
    _db(c, "delete from consents where user_id=? and type='profile_publication'", uid)
    assert _kinds(c, e) == []


def test_limit_validation(world):
    c, e, *_ = world
    assert c.get("/employer/activity?limit=0", headers=e).status_code == 422
    assert c.get("/employer/activity?limit=101", headers=e).status_code == 422
