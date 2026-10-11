"""События аналитики подбора: категории, потребности, приглашения, отклики, шорт-лист."""

import json
import sqlite3
import uuid

import test_analytics as ta
import test_shortlist as tsl
from app.analytics import service
from app.analytics.mapper import map_event
from fsp_contracts import new_event
from fsp_contracts.analytics import validate_event
from fsp_contracts.assessment import CategoryChanged, CategoryRef
from fsp_contracts.enums import DeclineReason, OfferStatus
from fsp_contracts.hiring import OfferInitiator

db, c, market_with_shortlist = ta.db, tsl.c, tsl.market_with_shortlist
_hdr, _create_need = tsl._hdr, tsl._create_need
SALT = "dev-only-analytics-salt"


def _map(name, payload):
    out = map_event(new_event(name, "core", payload), "salt")
    for ev in out:
        validate_event(ev)  # props проходят строгую схему
    return out


def test_invite_sent_and_answered_without_pii():
    offer = ta._offer(OfferStatus.sent)
    sent = {e.event: e for e in _map("offer.sent", offer)}
    assert sent["invite_sent"].props == {"invite_id": str(offer.offer_id), "with_vacancy": True}
    assert sent["invite_sent"].role == "employer"
    assert "offer_sent" in sent  # прежние события не потеряны

    no_vac = ta._offer(OfferStatus.sent).model_copy(update={"vacancy_id": None})
    invite = [e for e in _map("offer.sent", no_vac) if e.event == "invite_sent"][0]
    assert invite.props["with_vacancy"] is False

    dec = ta._offer(OfferStatus.declined, decline_reason=DeclineReason.low_salary)
    ans = [e for e in _map("offer.declined", dec) if e.event == "invite_answered"][0]
    assert ans.props["decision"] == "declined" and ans.props["reason"] == "low_salary"
    assert str(dec.candidate_id) not in json.dumps(ans.props)

    exp = [e for e in _map("offer.expired", ta._offer(OfferStatus.expired, actor="system"))]
    assert [e.props["decision"] for e in exp] == ["expired"]
    acc = _map("offer.accepted", ta._offer(OfferStatus.accepted, actor="candidate"))
    assert {e.event for e in acc} == {"offer_accepted", "invite_answered"}
    assert _map("offer.viewed", ta._offer(OfferStatus.viewed))[0].event == "offer_opened"


def test_response_created_and_answered():
    kw = {"initiator": OfferInitiator.candidate}
    created = _map("offer.sent", ta._offer(OfferStatus.sent, actor="candidate", **kw))
    assert [e.event for e in created] == ["response_created"]
    assert set(created[0].props) == {"response_id", "vacancy_id"}

    yes = _map(
        "offer.status_changed",
        ta._offer(OfferStatus.interview, actor="company", prev_status=OfferStatus.sent, **kw),
    )
    assert [(e.event, e.props["decision"]) for e in yes] == [("response_answered", "accepted")]
    no = _map(
        "offer.status_changed",
        ta._offer(OfferStatus.not_hired, actor="company", prev_status=OfferStatus.viewed, **kw),
    )
    assert no[0].props["decision"] == "declined"
    # hired после interview — не новый ответ; просмотр и отзыв в метрики не идут
    later = ta._offer(OfferStatus.hired, actor="company", prev_status=OfferStatus.interview, **kw)
    assert _map("offer.status_changed", later) == []
    assert _map("offer.viewed", ta._offer(OfferStatus.viewed, **kw)) == []
    assert _map("offer.withdrawn", ta._offer(OfferStatus.withdrawn, **kw)) == []


def test_category_changed_per_category_and_redelivery(db):
    path, factory = db
    cons = ta._consumer(factory)
    ev = CategoryChanged(
        candidate_id=uuid.uuid4(), profile_version=2,
        categories=[CategoryRef(profession="backend", grade="middle")],
    )  # fmt: skip
    env = new_event("candidate.category.changed", "core", ev)
    ta._dispatch(cons, env, times=3)
    rows = ta._rows(path)
    assert [r[0] for r in rows] == ["category_changed"]
    assert json.loads(rows[0][3]) == {
        "profession": "backend", "grade": "middle", "trigger": "recompute",
    }  # fmt: skip
    assert rows[0][1] == service.pseudonym(
        SALT.replace("dev-only-analytics-salt", ta.SALT), ev.candidate_id
    )


def test_invite_redelivery_does_not_duplicate(db):
    path, factory = db
    cons = ta._consumer(factory)
    env = new_event("offer.sent", "core", ta._offer(OfferStatus.sent))
    ta._dispatch(cons, env, times=3)
    names = [r[0] for r in ta._rows(path)]
    assert sorted(names) == ["invite_sent", "offer_received", "offer_sent"]


def _events(c):
    with sqlite3.connect(c.db) as con:
        rows = con.execute(
            "select event, actor, props from analytics_events order by id"
        ).fetchall()
    return [(e, a, json.loads(p)) for e, a, p in rows]


def test_need_and_shortlist_events(c, market_with_shortlist):
    h = market_with_shortlist
    text = "ищу секретный-запрос python"
    need = _create_need(c, h, text=text, filters={"skills_must": [{"slug": "python"}]}).json()
    ev = _events(c)
    assert [e[0] for e in ev] == ["need_created", "need_categories_shown"]
    assert ev[0][2]["need_id"] == need["id"] and ev[0][2]["skills"] >= 1
    assert ev[1][2]["categories"] == len(need["categories"])
    assert text not in json.dumps(ev) and all(e[1].startswith("a_") for e in ev)

    c.get(f"/needs/{need['id']}/categories", headers=_hdr(h))
    page = c.get(f"/categories/backend/middle/candidates?need_id={need['id']}", headers=_hdr(h))
    pseudo = page.json()["items"][0]["pseudo_id"]
    names = [e[0] for e in _events(c)]
    assert names[2:] == ["need_categories_shown", "category_viewed"]

    url = f"/needs/{need['id']}/shortlist/{pseudo}"
    assert c.post(url, headers=_hdr(h)).status_code == 204
    assert c.post(url, headers=_hdr(h)).status_code == 204  # повтор — без второго события
    assert c.delete(url, headers=_hdr(h)).status_code == 204
    assert c.delete(url, headers=_hdr(h)).status_code == 204
    tail = [e for e in _events(c) if e[0].startswith("shortlist_")]
    assert [(e[0], e[2]["size"]) for e in tail] == [
        ("shortlist_added", 1),
        ("shortlist_removed", 0),
    ]
    assert pseudo not in json.dumps(tail)
