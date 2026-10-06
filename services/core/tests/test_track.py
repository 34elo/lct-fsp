"""`POST /track` и `/internal/track` (E18-2): права, дедупликация, схемы, ПДн."""

import sqlite3
import uuid

import fakeredis
import pytest
from app.analytics import router as track_router
from app.analytics.service import pseudonym
from app.config import Settings
from app.main import build_app
from core_helpers import register
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

TS = "2026-10-05T12:00:00.123Z"
BOT = {"Authorization": "Service bot-tok"}


def ev(name="card_dwell", props=None, **kw):
    return {
        "event": name,
        "ts": TS,
        "props": props if props is not None else {"seconds": 3.5},
        **kw,
    }


def rows(api, sql="select event, actor, role, channel, props from analytics_events order by id"):
    with sqlite3.connect(api.db_path) as con:
        return con.execute(sql).fetchall()


@pytest.fixture
def bot_api(db_path):
    app = build_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            ui_bus_enabled=False,
            service_token_bot="bot-tok",
        )
    )
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db_path = db_path
        yield client


def test_anonymous_batch_is_stored(api):
    r = api.post("/track", json={"events": [ev(), ev("market_cell_clicked", {"role": "backend"})]})
    assert r.status_code == 202
    assert r.json() == {"accepted": 2, "rejected": 0, "duplicate": False}
    got = rows(api)
    assert [(g[0], g[1], g[2], g[3]) for g in got] == [
        ("card_dwell", None, "anon", "web"),
        ("market_cell_clicked", None, "anon", "web"),
    ]


def test_actor_and_role_are_set_by_server(api):
    h = register(api, "employer")
    r = api.post("/track", json={"events": [ev()]}, headers=h)
    assert r.json()["accepted"] == 1
    _, actor, role, channel, _ = rows(api)[0]
    assert role == "employer" and channel == "web"
    assert actor.startswith("a_") and len(actor) == 34


def test_client_cannot_set_actor_role_channel(api):
    for field, value in (("actor", "a_" + "0" * 16), ("role", "fsp_admin"), ("channel", "tg")):
        r = api.post("/track", json={"events": [{**ev(), field: value}]})
        assert r.status_code == 422
    assert rows(api) == []


def test_beacon_token_in_body(api):
    h = register(api)
    token = h["Authorization"].split()[1]
    api.post("/track", json={"events": [ev()], "access_token": token})
    assert rows(api)[0][2] == "candidate"
    api.post("/track", json={"events": [ev()], "access_token": "garbage"})
    assert rows(api)[1][2] == "anon"


def test_unknown_server_only_and_pii_props_are_rejected(api):
    batch = [
        ev("no_such_event", {}),
        ev("offer_accepted", {"offer_id": str(uuid.uuid4())}),  # серверное событие
        ev("card_dwell", {"seconds": 1, "email": "ivan@example.test"}),  # лишнее поле
        ev("card_dwell", {"seconds": 1, "name": "Иван Петров"}),
        ev("chip_edited", {"key": "Иван Петров", "source": "rule"}),  # не slug
        ev("card_dwell", {"seconds": 2}),
    ]
    r = api.post("/track", json={"events": batch})
    assert r.status_code == 202
    assert r.json() == {"accepted": 1, "rejected": 5, "duplicate": False}
    assert [g[0] for g in rows(api)] == ["card_dwell"]
    assert "ivan" not in str(rows(api)).lower()


def test_batch_limits(api):
    assert api.post("/track", json={"events": []}).status_code == 422
    assert api.post("/track", json={"events": [ev()] * 51}).status_code == 422
    assert api.post("/track", json={"events": [ev()] * 50}).json()["accepted"] == 50


def test_naive_ts_rejected(api):
    r = api.post("/track", json={"events": [{**ev(), "ts": "2026-10-05T12:00:00"}]})
    assert r.json() == {"accepted": 0, "rejected": 1, "duplicate": False}


def test_repeated_batch_id_is_idempotent(api):
    body = {"events": [ev()], "batch_id": "batch-0001-abcd"}
    assert api.post("/track", json=body).json()["accepted"] == 1
    again = api.post("/track", json=body)
    assert again.status_code == 202 and again.json()["duplicate"] is True
    assert len(rows(api)) == 1
    other = api.post("/track", json={**body, "batch_id": "batch-0002-abcd"})
    assert other.json()["accepted"] == 1 and len(rows(api)) == 2


def test_rate_limit(api, monkeypatch):
    monkeypatch.setattr(track_router, "RATE_LIMIT", 2)
    codes = [api.post("/track", json={"events": [ev()]}).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_internal_requires_service_token(bot_api):
    body = {"events": [ev("uplift_shown", {"skill": "python"})]}
    assert bot_api.post("/internal/track", json=body).status_code == 401
    bad = bot_api.post("/internal/track", json=body, headers={"Authorization": "Service x"})
    assert bad.status_code == 401
    jwt = {"Authorization": "Bearer abc"}
    assert bot_api.post("/internal/track", json=body, headers=jwt).status_code == 401
    assert rows(bot_api) == []


def test_internal_closed_when_token_not_configured(api):
    r = api.post("/internal/track", json={"events": [ev("uplift_shown", {"skill": "python"})]})
    assert r.status_code == 401


def test_internal_bot_events(bot_api):
    uid = uuid.uuid4()
    body = {
        "events": [
            {
                **ev("uplift_clicked", {"skill": "python", "action": "test"}),
                "user_id": str(uid),
                "role": "candidate",
            },
            ev("uplift_shown", {"skill": "go"}),
            ev("card_dwell", {"seconds": 1}),  # только web: боту нельзя
        ],
        "batch_id": "bot-batch-0001",
    }
    r = bot_api.post("/internal/track", json=body, headers=BOT)
    assert r.status_code == 202 and r.json()["accepted"] == 2 and r.json()["rejected"] == 1
    got = rows(bot_api)
    assert got[0][1] == pseudonym("dev-only-analytics-salt", uid)
    assert got[0][2:4] == ("candidate", "tg")
    assert got[1][1:4] == (None, "anon", "tg")
    assert bot_api.post("/internal/track", json=body, headers=BOT).json()["duplicate"] is True
    assert len(rows(bot_api)) == 2


def test_web_cannot_send_bot_events_as_other_user(api):
    r = api.post("/track", json={"events": [{**ev(), "user_id": str(uuid.uuid4())}]})
    assert r.status_code == 422
