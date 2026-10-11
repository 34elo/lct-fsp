"""`GET /public/stats`: агрегаты для лендинга без ПДн, без авторизации, кеш 5 минут."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.views.public_stats import median_days
from factories.base import make_candidate, make_company, make_grade, make_vacancy
from factories.hiring import make_offer
from fsp_platform.db import session_scope

KEYS = {"candidates", "companies", "invitations", "median_days_to_invite"}


def test_empty_database_returns_nulls_without_auth(api):
    r = api.get("/public/stats")
    assert r.status_code == 200
    assert r.json() == dict.fromkeys(KEYS)
    assert "max-age=300" in r.headers["cache-control"]


async def test_counts_and_median_without_pii(api, factory):
    async with session_scope(factory) as s:
        company, owner = await make_company(s, status="verified")
        await make_company(s, status="pending")  # на модерации в цифры не входит
        vac = await make_vacancy(s, company)
        first = await make_candidate(s)
        await make_grade(s, first.user_id)
        second = await make_candidate(s)
        await make_grade(s, second.user_id)
        await make_candidate(s)  # без теста не считается
        await make_offer(
            s, vac, first.user_id, owner.id, created_at=datetime.now(UTC) + timedelta(days=3)
        )
    r = api.get("/public/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["candidates"] == 2
    assert body["companies"] == 1
    assert body["invitations"] == 1
    assert body["median_days_to_invite"] == 3


async def test_response_is_cached_for_five_minutes(api, factory):
    assert api.get("/public/stats").json()["candidates"] is None
    async with session_scope(factory) as s:
        cand = await make_candidate(s)
        await make_grade(s, cand.user_id)
    assert api.get("/public/stats").json()["candidates"] is None  # из кеша
    ttl = await api.app.state.redis.ttl("c:public:stats")
    assert 0 < ttl <= 300
    await api.app.state.redis.delete("c:public:stats")
    assert api.get("/public/stats").json()["candidates"] == 1


def test_median_days_uses_only_candidates_with_both_dates():
    base = datetime(2026, 10, 1, tzinfo=UTC)
    a, b, c = uuid4(), uuid4(), uuid4()
    graded = {a: base, b: base, c: base}
    invited = {a: base + timedelta(days=2), b: base + timedelta(days=6), uuid4(): base}
    assert median_days(graded, invited) == 4
    assert median_days(graded, {}) is None
