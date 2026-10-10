"""Дашборд ФСП (E18-3): воронка, скрытие малых ячеек, права, нет ПДн."""

import asyncio
import sqlite3
from datetime import UTC, datetime

from app.analytics import service
from core_helpers import register
from fsp_contracts.analytics import AnalyticsEvent
from fsp_platform.db import make_engine, make_session_factory, session_scope

OFFER = "00000000-0000-0000-0000-000000000001"


def admin(api):
    h = register(api, "employer")
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin'")
    return h


def act(i):
    return f"a_{i:032x}"


def push(api, items, source="server"):
    """items: [(event, actor, props)]."""

    async def go():
        engine = make_engine(f"sqlite+aiosqlite:///{api.db_path}")
        async with session_scope(make_session_factory(engine)) as s:
            now = datetime.now(UTC)
            await service.record(
                s,
                [
                    AnalyticsEvent(
                        event=e, ts=now, actor=a, role="candidate", channel="system", props=p
                    )
                    for e, a, p in items
                ],
                source=source,
            )
        await engine.dispose()

    asyncio.run(go())


def test_requires_fsp_admin(api):
    assert api.get("/admin/dashboard").status_code == 401
    cand = register(api, "candidate")
    assert api.get("/admin/dashboard", headers=cand).status_code == 403


def test_small_cells_hidden(api):
    h = admin(api)
    push(api, [("signup_completed", act(i), {"channel": "web"}) for i in range(4)])
    body = api.get("/admin/dashboard", headers=h).json()
    reg = body["funnel"][0]
    assert reg["hidden"] and reg["count"] is None
    assert body["fsp_share"]["pct"] is None and body["fsp_share"]["of"] is None


def test_funnel_counts_and_shares(api):
    h = admin(api)
    ev = []
    for i in range(10):
        a = act(i)
        ev.append(("signup_completed", a, {"channel": "web"}))
        if i < 8:
            ev.append(("test_completed", a, {"skill": "python"}))
        if i < 6:
            props = {"profile_version": 1, "skills_up": 0, "grade_to": "middle"}
            ev.append(("profile_updated", a, props))
        if i < 5:
            ev.append(("offer_received", a, {"offer_id": OFFER}))
            ev.append(("fsp_link_completed", a, {"method": "code", "verified": True}))
    # не из когорты регистраций окна: в воронку не попадает
    ev.append(("profile_updated", act(999), {"profile_version": 1, "skills_up": 0}))
    push(api, ev)
    web = [("uplift_shown", act(i), {"skill": "python"}) for i in range(6)]
    props = {"competition_id": "c1", "source": "navigator"}
    web += [("competition_clicked", act(i), props) for i in range(5)]
    push(api, web, source="web")
    body = api.get("/admin/dashboard", headers=h).json()
    by = {s["id"]: s for s in body["funnel"]}
    assert [by[k]["count"] for k in ("registered", "test", "category", "invited")] == [10, 8, 6, 5]
    assert by["answered"]["hidden"]  # 0 человек
    assert by["test"]["pct_of_registered"] == 80.0
    assert by["category"]["pct_of_previous"] == 75.0
    assert body["fsp_share"] == {"count": 5, "hidden": False, "pct": 50.0, "of": 10}
    nav = body["navigator_to_competition"]
    assert nav["count"] == 5 and nav["of"] == 6 and nav["pct"] == 83.3


def test_no_pii_or_actor_in_response(api):
    h = admin(api)
    push(api, [("signup_completed", act(i), {"channel": "web"}) for i in range(6)])
    r = api.get("/admin/dashboard", headers=h)
    assert act(3) not in r.text and "actor" not in r.text
    assert api.get("/admin/dashboard?days=0", headers=h).status_code == 422


def test_counters_and_daily_series(api):
    h = admin(api)
    ev = [("signup_completed", act(i), {"channel": "web"}) for i in range(6)]
    ev += [("interest_shown", act(100 + i), {}) for i in range(2)]
    push(api, ev)
    body = api.get("/admin/dashboard", headers=h).json()
    cnt = {c["id"]: c for c in body["counters"]}
    assert cnt["registrations"]["count"] == 6
    assert cnt["interests"]["hidden"] and cnt["interests"]["count"] is None
    assert len(body["daily"]) == body["days"] + 1
    today = body["daily"][-1]["values"]
    assert today["registrations"] == 6 and today["interests"] is None
