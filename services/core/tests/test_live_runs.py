"""Живые прогоны: создание, автозасчёт заданий по событиям, SUS, права."""

import asyncio
import sqlite3

from app.analytics import service
from core_helpers import register
from fsp_contracts.analytics import AnalyticsEvent
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import text

TS = "2026-10-05T12:00:00Z"
T2 = "2026-10-05T12:01:30Z"


def admin(api):
    h = register(api, "employer")
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin'")  # единственный пользователь теста
    return h


def make(api, h, scenario="candidate", **kw):
    r = api.post("/admin/live-runs", json={"scenario": scenario, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def track(api, run_id, name, props=None, ts=TS, headers=None):
    ev = {"event": name, "ts": ts, "run_id": run_id, "props": props or {}}
    r = api.post("/track", json={"events": [ev]}, headers=headers or {})
    assert r.status_code == 202, r.text
    return r.json()


def push_server_events(api, name, n=1):
    """Серверные события (источник server) без run_id: как из очереди core.analytics."""

    async def go():
        engine = make_engine(f"sqlite+aiosqlite:///{api.db_path}")
        async with session_scope(make_session_factory(engine)) as s:
            actor = (await s.execute(text("select actor from live_runs"))).scalar_one()
            evs = [
                AnalyticsEvent(
                    event=name, ts="2099-01-01T00:00:00Z", actor=actor,
                    role="candidate", channel="system", props={},
                )
                for _ in range(n)
            ]  # fmt: skip
            await service.record(s, evs)
        await engine.dispose()

    asyncio.run(go())


def state(api, token):
    return api.get(f"/run/{token}").json()


def test_create_and_public_state(api):
    h = admin(api)
    run = make(api, h)
    assert run["status"] == "invited" and run["path"] == f"/run/{run['token']}"
    assert [t["id"] for t in run["tasks"]] == ["resume", "fsp", "uplift", "offer_reply"]
    pub = state(api, run["token"])
    assert pub["id"] == run["id"] and not pub["all_done"]
    assert "token" not in pub and "notes" not in pub


def test_custom_tasks_and_unknown_task(api):
    h = admin(api)
    run = make(api, h, "employer", tasks=["offer_sent", "shortlist"])
    assert [t["id"] for t in run["tasks"]] == ["offer_sent", "shortlist"]
    bad = api.post("/admin/live-runs", json={"scenario": "employer", "tasks": ["nope"]}, headers=h)
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_tasks"


def test_admin_only(api):
    cand = register(api, "candidate")
    assert api.post("/admin/live-runs", json={"scenario": "candidate"}).status_code == 401
    assert (
        api.post("/admin/live-runs", json={"scenario": "candidate"}, headers=cand).status_code
        == 403
    )
    assert api.get("/admin/live-runs", headers=cand).status_code == 403


def test_unknown_token_is_404(api):
    assert api.get("/run/nope").status_code == 404
    assert api.post("/run/nope/start").status_code == 404
    body = {"answers": [3] * 10}
    assert api.post("/run/nope/sus", json=body).status_code == 404


def test_web_event_with_run_id_completes_task(api):
    h = admin(api)
    run = make(api, h)
    # веб-события: uplift_clicked допустим из web
    track(api, run["id"], "uplift_clicked", {"skill": "python"})
    pub = state(api, run["token"])
    assert [t["done"] for t in pub["tasks"]] == [False, False, True, False]
    got = api.get(f"/admin/live-runs/{run['id']}", headers=h).json()
    assert got["status"] == "started" and got["started_at"] and got["steps"] == 1
    assert got["tasks_done"] == 1


def test_server_events_matched_by_bound_actor(api):
    """Серверное событие без run_id попадает в прогон по псевдониму испытателя."""
    h = admin(api)
    tester = register(api, "candidate")
    run = make(api, h)
    # старт с токеном испытателя привязывает псевдоним
    assert api.post(f"/run/{run['token']}/start", headers=tester).json()["status"] == "started"

    push_server_events(api, "resume_confirmed")
    assert state(api, run["token"])["tasks"][0]["done"]
    with sqlite3.connect(api.db_path) as con:
        (rid,) = con.execute(
            "select run_id from analytics_events where event='resume_confirmed'"
        ).fetchone()
    assert rid.replace("-", "") == run["id"].replace("-", "")


def test_actor_bound_by_first_event_with_run_id(api):
    h = admin(api)
    tester = register(api, "candidate")
    run = make(api, h)
    track(api, run["id"], "uplift_shown", {"skill": "python"}, headers=tester)
    with sqlite3.connect(api.db_path) as con:
        (actor,) = con.execute("select actor from live_runs").fetchone()
    assert actor and actor.startswith("a_")


def test_employer_scenario_counts_and_dwell_threshold(api):
    h = admin(api)
    run = make(api, h, "employer")
    track(api, run["id"], "card_dwell", {"seconds": 5})  # слишком коротко
    assert not state(api, run["token"])["tasks"][1]["done"]
    track(api, run["id"], "card_dwell", {"seconds": 25}, ts=T2)
    assert state(api, run["token"])["tasks"][1]["done"]
    track(api, run["id"], "graph_path_highlighted", {"requirement": "python"})  # задание уже done
    got = api.get(f"/admin/live-runs/{run['id']}", headers=h).json()
    why = got["tasks"][1]
    assert why["count"] == 1 and why["duration_s"] == 90


def test_shortlist_needs_five(api):
    h = admin(api)
    run = make(api, h, "employer", tasks=["shortlist"])
    tester = register(api, "employer")
    api.post(f"/run/{run['token']}/start", headers=tester)

    push_server_events(api, "shortlisted", 4)
    t = state(api, run["token"])["tasks"][0]
    assert (t["count"], t["done"]) == (4, False)
    push_server_events(api, "shortlisted")
    assert state(api, run["token"])["all_done"]


def test_sus_score_finishes_run_once(api):
    h = admin(api)
    run = make(api, h)
    best = [5, 1] * 5  # нечётные 5, чётные 1 -> 100
    r = api.post(
        f"/run/{run['token']}/sus", json={"answers": best, "category_agree": True, "notes": "ок"}
    )
    assert r.status_code == 200 and r.json()["status"] == "finished"
    got = api.get(f"/admin/live-runs/{run['id']}", headers=h).json()
    assert got["sus_score"] == 100.0 and got["category_agree"] is True and got["finished_at"]
    again = api.post(f"/run/{run['token']}/sus", json={"answers": best})
    assert again.status_code == 409
    # после завершения события в прогон уже не попадают
    track(api, run["id"], "uplift_clicked", {"skill": "python"})
    assert api.get(f"/admin/live-runs/{run['id']}", headers=h).json()["tasks_done"] == 0


def test_sus_validation_and_formula(api):
    h = admin(api)
    run = make(api, h)
    for bad in ([3] * 9, [3] * 11, [0] + [3] * 9, [6] + [3] * 9):
        assert api.post(f"/run/{run['token']}/sus", json={"answers": bad}).status_code == 422
    from app.analytics.runs import sus_score

    assert sus_score([3] * 10) == 50.0
    assert sus_score([1, 5] * 5) == 0.0


def test_list_summary(api):
    h = admin(api)
    a, b = make(api, h), make(api, h, "employer")
    track(api, a["id"], "uplift_clicked", {"skill": "python"})
    api.post(f"/run/{a['token']}/sus", json={"answers": [5, 1] * 5, "category_agree": False})
    got = api.get("/admin/live-runs", headers=h).json()
    assert {i["id"] for i in got["items"]} == {a["id"], b["id"]}
    s = got["summary"]
    assert s["runs"] == 2 and s["finished"] == 1
    assert s["task_success_pct"] == 25.0 and s["median_sus"] == 100.0
    assert s["category_agree_pct"] == 0.0
    only = api.get("/admin/live-runs?scenario=employer", headers=h).json()
    assert [i["id"] for i in only["items"]] == [b["id"]]
