"""core.analytics: доменные события → analytics_events."""

import asyncio
import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from app.analytics import handlers, service
from app.analytics.mapper import MAPPERS, map_event
from core_helpers import upgrade_head
from fsp_contracts import new_event
from fsp_contracts.enums import DeclineReason, OfferStatus
from fsp_contracts.events import (
    CandidateDeleted,
    CandidateRegistered,
    FspLinked,
    MatchesReady,
    OfferEvent,
    ProfileDiff,
    SkillsProfileUpdated,
)
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.messaging import QUEUES, Consumer

CORE = Path(__file__).resolve().parents[1]
SALT = "test-salt"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "a.db"
    url = f"sqlite+aiosqlite:///{path}"
    upgrade_head(url)
    return path, make_session_factory(make_engine(url))


def _rows(path, sql="select event, actor, role, props from analytics_events order by id"):
    with sqlite3.connect(path) as con:
        return con.execute(sql).fetchall()


def _consumer(factory):
    consumers = {"core.analytics": Consumer(QUEUES["core.analytics"])}
    handlers.register(consumers, factory, SALT)
    return consumers["core.analytics"]


def _dispatch(consumer, env, times=1):
    for _ in range(times):
        asyncio.run(consumer.dispatch(env))


def _offer(status, **kw):
    return OfferEvent(
        offer_id=uuid.uuid4(), candidate_id=uuid.uuid4(), company_id=uuid.uuid4(),
        vacancy_id=uuid.uuid4(), status=status, **kw,
    )  # fmt: skip


def test_queue_bound_to_all_events():
    assert QUEUES["core.analytics"].bindings == ("#",)


def test_pseudonym_is_stable_and_salted():
    uid = uuid.uuid4()
    assert service.pseudonym("a", uid) == service.pseudonym("a", uid)
    assert service.pseudonym("a", uid) != service.pseudonym("b", uid)
    assert str(uid).replace("-", "")[:8] not in service.pseudonym("a", uid)


def test_offer_sent_writes_two_events_without_pii(db):
    path, factory = db
    c = _consumer(factory)
    ev = _offer(OfferStatus.sent)
    _dispatch(c, new_event("offer.sent", "core", ev))
    rows = _rows(path)
    assert [r[0] for r in rows] == ["offer_sent", "offer_received", "invite_sent"]
    assert [r[2] for r in rows] == ["employer", "candidate", "employer"]
    dump = json.dumps(rows)
    assert str(ev.candidate_id) not in dump and str(ev.company_id) not in dump
    assert rows[1][1] == service.pseudonym(SALT, ev.candidate_id)
    assert json.loads(rows[0][3]) == {"offer_id": str(ev.offer_id)}


def test_redelivery_does_not_duplicate(db):
    path, factory = db
    c = _consumer(factory)
    offer = _offer(OfferStatus.declined, decline_reason=DeclineReason.low_salary, actor="candidate")
    env = new_event("offer.declined", "core", offer)
    _dispatch(c, env, times=3)
    rows = _rows(path)
    assert [r[0] for r in rows] == ["offer_declined", "invite_answered"]
    assert all(json.loads(r[3])["reason"] == "low_salary" for r in rows)


def test_offer_message_only_from_candidate(db):
    path, factory = db
    c = _consumer(factory)
    mid = uuid.uuid4()
    _dispatch(c, new_event("offer.message", "core", _offer(
        OfferStatus.sent, actor="company", message_id=mid)))  # fmt: skip
    assert _rows(path) == []
    _dispatch(c, new_event("offer.message", "core", _offer(
        OfferStatus.sent, actor="candidate", message_id=mid)))  # fmt: skip
    assert [r[0] for r in _rows(path)] == ["offer_question_asked"]


def test_profile_updated_and_misc_mappings(db):
    path, factory = db
    c = _consumer(factory)
    cid = uuid.uuid4()
    diff = ProfileDiff.model_validate(
        {
            "skills_up": [{"slug": "python", "from": 2, "to": 3}],
            "grade": {"from": "junior", "to": "middle"},
        }
    )
    _dispatch(c, new_event("skills.profile.updated", "core",
        SkillsProfileUpdated(candidate_id=cid, profile_version=3, diff=diff)))  # fmt: skip
    _dispatch(c, new_event("candidate.registered", "core",
        CandidateRegistered(candidate_id=cid, channel="tg")))  # fmt: skip
    linked = FspLinked(candidate_id=cid, participant_id="p-secret-1", verified=True, method="oauth")
    _dispatch(c, new_event("fsp.linked", "fsp-connector", linked))
    ready = MatchesReady(vacancy_id=uuid.uuid4(), count=7)
    _dispatch(c, new_event("matches.ready", "core", ready))
    rows = _rows(path)
    assert [r[0] for r in rows] == [
        "profile_updated", "signup_completed", "fsp_link_completed", "matches_computed",
    ]  # fmt: skip
    assert json.loads(rows[0][3]) == {
        "profile_version": 3, "skills_up": 1, "skills_new": 0,
        "grade_to": "middle", "grade_from": "junior",
    }  # fmt: skip
    assert "p-secret-1" not in json.dumps(rows)


def test_unmapped_events_are_ignored(db):
    path, factory = db
    c = _consumer(factory)
    assert "taxonomy.updated" not in c.handlers
    _dispatch(c, new_event("candidate.preferences.updated", "core",
        __import__("fsp_contracts.events", fromlist=["x"]).CandidatePreferencesUpdated(
            candidate_id=uuid.uuid4(), fields=["salary_min"])))  # fmt: skip
    assert _rows(path) == []


def test_candidate_deleted_removes_raw_events(db):
    path, factory = db
    c = _consumer(factory)
    cid, other = uuid.uuid4(), uuid.uuid4()
    for who in (cid, other):
        _dispatch(c, new_event("candidate.registered", "core",
            CandidateRegistered(candidate_id=who, channel="web")))  # fmt: skip
    assert len(_rows(path)) == 2
    _dispatch(c, new_event("candidate.deleted", "core", CandidateDeleted(candidate_id=cid)), 2)
    rows = _rows(path)
    assert [r[1] for r in rows] == [service.pseudonym(SALT, other)]


def test_every_mapper_has_known_event_types():
    from fsp_contracts.events import EVENTS

    assert set(MAPPERS) <= set(EVENTS)


def test_map_event_unknown_returns_empty():
    env = new_event("taxonomy.updated", "core", __import__(
        "fsp_contracts.events", fromlist=["x"]).TaxonomyUpdated(version=1))  # fmt: skip
    assert map_event(env, SALT) == []
