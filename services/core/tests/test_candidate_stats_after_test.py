"""E43-5: свежий кандидат после теста получает место в категории и просмотры (без демо-сида)."""
# ruff: noqa: F811

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from app.views.models import ProfileView
from core_helpers import register
from fsp_platform.db import session_scope
from test_assessment_grades import _run, _start, fake_bank, taxonomy_loaded  # noqa: F401


def _uid(h) -> uuid.UUID:
    tok = h["Authorization"][7:]
    return uuid.UUID(jwt.decode(tok, options={"verify_signature": False})["sub"])


def _passed(api):
    h = register(api)
    _run(api, h, _start(api, h).json()["id"])
    return h


async def test_fresh_candidate_gets_percentile_and_category(api, taxonomy_loaded, fake_bank):
    h = register(api)
    empty = api.get("/candidates/me/standing", headers=h)
    assert empty.status_code == 200 and empty.json().get("strength") is None
    _run(api, h, _start(api, h).json()["id"])
    body = api.get("/candidates/me/standing", headers=h).json()
    assert (body["profession"], body["grade"]) == ("backend", "middle")
    assert body["strength"]["rank"] == 1 and body["strength"]["top_percent"] == 100
    assert body["category_size"] == 1 and body["peers"][0]["strength"] == body["strength"]["value"]


async def test_standing_not_stale_when_category_changes(api, taxonomy_loaded, fake_bank):
    """Статистика не кешируется: новый участник категории виден сразу."""
    h = _passed(api)
    assert api.get("/candidates/me/standing", headers=h).json()["category_size"] == 1
    _passed(api)
    after = api.get("/candidates/me/standing", headers=h).json()
    assert after["category_size"] == 2 and len(after["peers"]) == 2


async def test_views_full_scale_and_visibility(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    zero = api.get("/candidates/me/views", headers=h).json()
    assert zero["visible"] is False and zero["total_30d"] == 0
    assert len(zero["by_day"]) == 30 and {d["count"] for d in zero["by_day"]} == {0}
    _run(api, h, _start(api, h).json()["id"])
    assert api.get("/candidates/me/views", headers=h).json()["visible"] is False  # нет согласия
    body = {"consents": [{"type": "pd_processing", "granted": True},
                         {"type": "profile_publication", "granted": True}]}  # fmt: skip
    assert api.put("/me/consents", json=body, headers=h).status_code == 200
    v = api.get("/candidates/me/views", headers=h).json()
    assert v["visible"] is True and v["window_days"] == 30
    async with session_scope(factory) as s:
        s.add(ProfileView(candidate_id=_uid(h), company_id=uuid.uuid4(), source="search",
                          viewed_at=datetime.now(UTC) - timedelta(days=1)))  # fmt: skip
    v = api.get("/candidates/me/views", headers=h).json()
    assert (v["total_30d"], v["companies_30d"]) == (1, 1)
    days = [d["date"] for d in v["by_day"]]
    assert days == sorted(days) and len(days) == 30
    assert sum(d["count"] for d in v["by_day"]) == 1 and v["by_day"][-2]["count"] == 1
