"""Подписка на категорию: уведомление о новом подходящем кандидате (E33-4)."""

import asyncio
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_search as ts
from app.matching import needs as n
from app.matching import subscriptions
from app.notifications.handlers import register
from fsp_contracts import new_envelope
from fsp_contracts.assessment import CategoryChanged, CategoryRef
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.messaging import QUEUES, Consumer

c = ts.c
_cand, _employer, _hdr = ts._cand, ts._employer, ts._hdr


@pytest.fixture
def world(c):
    h = _employer(c, "e@x.ru")
    with sqlite3.connect(c.db) as con:
        con.execute("insert into roles (slug, name) values ('backend', 'Backend')")
        con.execute("insert into roles (slug, name) values ('ml', 'ML')")
    c.factory = make_session_factory(make_engine(f"sqlite+aiosqlite:///{c.db}"))
    c.ui = []
    return h


def _sub(c, h, **body):
    body.setdefault("profession", "backend")
    return c.post("/subscriptions", json=body, headers=_hdr(h))


def _event(cand_hex, profession="backend", grade="middle", repeat=1):
    uid = uuid.UUID(cand_hex)
    env = new_envelope(
        "candidate.category.changed", "core",
        CategoryChanged(
            candidate_id=uid, categories=[CategoryRef(profession=profession, grade=grade)],
            profile_version=1,
        ),
    )  # fmt: skip
    return env, repeat


def _deliver(c, cand_hex, **kw):
    env, repeat = _event(cand_hex, **kw)
    consumers = {"core.handlers": Consumer(QUEUES["core.handlers"])}

    async def publish(msg):
        c.ui.append(msg)

    register(consumers, c.factory, publish)
    for _ in range(repeat):
        asyncio.run(consumers["core.handlers"].dispatch(env))


def _notes(c):
    with sqlite3.connect(c.db) as con:
        return con.execute(
            "select type, payload from notifications where type='category_subscription'"
        ).fetchall()


def test_subscription_crud_and_validation(c, world):
    r = _sub(c, world, grades=["middle"], skills=[{"slug": "python", "min_level": 3}],
             salary_max=250_000, formats=["remote"], only_confirmed=True)  # fmt: skip
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["grades"] == ["middle"] and body["skills"][0]["min_level"] == 3
    assert [s["id"] for s in c.get("/subscriptions", headers=_hdr(world)).json()] == [body["id"]]
    assert _sub(c, world, profession="nope").status_code == 422
    assert _sub(c, world, skills=[{"slug": "cobol"}]).status_code == 422
    assert _sub(c, world, grades=["lead"]).status_code == 422
    assert c.delete(f"/subscriptions/{body['id']}", headers=_hdr(world)).status_code == 204
    assert c.get("/subscriptions", headers=_hdr(world)).json() == []


def test_foreign_subscription_is_404(c, world):
    sid = _sub(c, world).json()["id"]
    other = _employer(c, "o@x.ru", name="Other")
    assert c.get("/subscriptions", headers=_hdr(other)).json() == []
    assert c.delete(f"/subscriptions/{sid}", headers=_hdr(other)).status_code == 404
    assert c.delete(f"/subscriptions/{uuid.uuid4()}", headers=_hdr(world)).status_code == 404


def test_subscription_limit(c, world, monkeypatch):
    monkeypatch.setattr(
        "app.matching.subscriptions_router._NEEDS", n.NeedsConfig(max_subscriptions=1)
    )
    assert _sub(c, world).status_code == 201
    assert _sub(c, world).status_code == 429


def test_new_candidate_notifies_once_without_pii(c, world):
    _sub(c, world, grades=["middle"], skills=[{"slug": "python", "min_level": 3}])
    uid = _cand(c, 1, [("python", 0.8, 3, ["test"])], salary_min=200_000)
    _deliver(c, uid, repeat=3)  # повтор события не дублирует
    (note,) = _notes(c)
    payload = json.loads(note[1])
    assert payload["count"] == 1 and payload["pseudo_ids"] == ["pid0001"]
    assert "Backend #1" not in note[1]  # псевдоним/ПДн в уведомление не кладём
    assert [m.event for m in c.ui] == ["notification.new"]


@pytest.mark.parametrize(
    ("sub", "cand", "fits"),
    [
        ({"grades": ["senior"]}, {}, False),
        ({"skills": [{"slug": "python", "min_level": 4}]}, {}, False),
        ({"salary_max": 150_000}, {"salary_min": 200_000}, False),
        ({"salary_max": 250_000}, {"salary_min": 200_000}, True),
        ({"salary_max": 150_000}, {"salary_min": None}, True),  # вилка не указана — подходит
        ({"formats": ["office"]}, {}, False),
        ({"only_confirmed": True}, {}, True),
        ({}, {"search_status": "dnd"}, False),
    ],
)
def test_filters(c, world, sub, cand, fits):
    _sub(c, world, **sub)
    uid = _cand(c, 1, [("python", 0.8, 3, ["test"])], **cand)
    _deliver(c, uid)
    assert bool(_notes(c)) is fits


def test_only_confirmed_skips_unconfirmed_grade(c, world):
    _sub(c, world, only_confirmed=True)
    uid = _cand(c, 1, [("python", 0.8, 3, ["test"])])
    with sqlite3.connect(c.db) as con:
        con.execute("update grades set needs_confirmation=1")
    _deliver(c, uid)
    assert _notes(c) == []


def test_stoplist_and_hidden_candidate(c, world):
    _sub(c, world)
    stop = _cand(c, 1, stoplist_company_ids=[world["company_id"]])
    untested = _cand(c, 2, tested=False)  # без грейда из теста кандидата нет
    _deliver(c, stop)
    _deliver(c, untested)
    assert _notes(c) == []


def test_other_profession_does_not_notify(c, world):
    _sub(c, world, profession="ml")
    _deliver(c, _cand(c, 1, [("python", 0.8, 3, ["test"])]))
    assert _notes(c) == []


def test_digest_not_more_than_once_per_interval(c, world):
    _sub(c, world)
    _deliver(c, _cand(c, 1))
    _deliver(c, _cand(c, 2))  # в пределах часа: копится
    assert len(_notes(c)) == 1
    cfg = n.NeedsConfig()

    async def flush(now):
        async with c.factory() as s:
            await subscriptions.flush_due(s, cfg, now=now)
            await s.commit()

    asyncio.run(flush(datetime.now(UTC) + timedelta(minutes=10)))
    assert len(_notes(c)) == 1  # интервал не прошёл
    asyncio.run(flush(datetime.now(UTC) + timedelta(minutes=61)))
    notes = _notes(c)
    assert len(notes) == 2 and json.loads(notes[1][1])["pseudo_ids"] == ["pid0002"]
    asyncio.run(flush(datetime.now(UTC) + timedelta(minutes=200)))
    assert len(_notes(c)) == 2  # всё отправлено
