"""Подстройка в сессии через API (E17-4): `/recs/feedback`, `/recs/sessions/{id}`, выдача."""

import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
NOW = datetime.now(UTC).isoformat(sep=" ")
UNTIL = (datetime.now(UTC) + timedelta(days=5)).isoformat(sep=" ")
ACTIVE = {5, 6}


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "c.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db = db
        yield client


def _user(c, email, role):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _employer(c, email, name="Acme Labs"):
    h = _user(c, email, "employer")
    co = c.post("/companies", json={"name": name, "inn": INN}, headers=h).json()
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update companies set status='verified' where id=?", (co["id"].replace("-", ""),)
        )
    return h


def _cand(c, n):
    uid = uuid.uuid4().hex
    active = n in ACTIVE
    row = dict(
        pseudonym=f"Backend #{n}", pseudo_id=f"pid{n:04d}", primary_role="backend",
        grade="middle", grade_confidence=0.75, formats=["remote"], employment_types=["full"],
        city="Москва", relocation=False, search_status="active" if active else "open",
        stoplist_company_ids=[], primary_stack=["python"], active_until=UNTIL if active else None,
    )  # fmt: skip
    cols = ["user_id", "visibility", "updated_at", *row]
    vals = [uid, "{}", NOW, *(json.dumps(v) if isinstance(v, list) else v for v in row.values())]
    with sqlite3.connect(c.db) as con:
        con.execute(
            f"insert into candidates ({','.join(cols)}) values ({','.join('?' * len(cols))})", vals
        )
    return uid


def _q(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


@pytest.fixture
def h(c):
    h = _employer(c, "e@x.ru")
    for n in range(1, 7):
        _cand(c, n)
    return h


def _search(c, h, sid):
    r = c.post("/search/candidates", json={"session_id": sid}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _fb(c, h, sid, pid, event, reason=None):
    body = {"session_id": sid, "candidate_pseudo_id": pid, "event": event, "reason": reason}
    r = c.post("/recs/feedback", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["tuning"]


def test_impressions_store_feature_snapshot(c, h):
    sid = str(uuid.uuid4())
    _search(c, h, sid)
    feats = [json.loads(f)["x"] for (f,) in _q(c, "select features from impressions")]
    assert len(feats) == 6
    assert set(feats[0]) == {
        "skills", "semantic", "grade", "salary", "fsp", "captain", "github", "active"
    }  # fmt: skip
    assert sorted(f["active"] for f in feats) == [0, 0, 0, 0, 1, 1]


def test_tuning_activates_after_three_signals_and_reorders(c, h):
    sid = str(uuid.uuid4())
    first = _search(c, h, sid)
    assert first.get("tuning") is None or first["tuning"]["active"] is False
    assert [i["pseudo_id"] for i in first["items"]][:2] == ["pid0001", "pid0002"]

    t = _fb(c, h, sid, "pid0005", "shortlist")
    assert (t["active"], t["signals"], t["min_signals"]) == (False, 1, 3)
    _fb(c, h, sid, "pid0001", "dismiss", "дорого")
    t = _fb(c, h, sid, "pid0002", "dismiss", "не тот стек")
    assert t["active"] is True and t["signals"] == 3
    w = {x["feature"]: x for x in t["weights"]}
    assert w["active"]["current"] > w["active"]["start"]
    assert t["chips"] == []  # рост < 25% — чипа ещё нет
    assert {x["kind"] for x in t["hints"]} == {"raise_budget", "make_skill_required"}
    _fb(c, h, sid, "pid0006", "shortlist")
    t = _fb(c, h, sid, "pid0003", "dismiss")
    assert [x["feature"] for x in t["chips"]] == ["active"]
    assert t["chips"][0]["text"].startswith("Учли: ")

    out = _search(c, h, sid)
    assert out["tuning"]["active"] is True and out["tuning"]["chips"]
    order = [i["pseudo_id"] for i in out["items"]]
    assert set(order[:2]) == {"pid0005", "pid0006"}  # жёсткие фильтры те же — только порядок
    assert sorted(order) == sorted(i["pseudo_id"] for i in first["items"])


def test_repeated_feedback_does_not_change_tuning(c, h):
    sid = str(uuid.uuid4())
    _search(c, h, sid)
    _fb(c, h, sid, "pid0005", "shortlist")
    _fb(c, h, sid, "pid0001", "dismiss")
    t1 = _fb(c, h, sid, "pid0002", "dismiss")
    t2 = _fb(c, h, sid, "pid0002", "dismiss")  # повторная доставка
    assert t1 == t2
    assert c.get(f"/recs/sessions/{sid}", headers=h).json() == t1


def test_get_and_reset_session(c, h):
    sid = str(uuid.uuid4())
    _search(c, h, sid)
    for pid, ev in (("pid0005", "shortlist"), ("pid0001", "dismiss"), ("pid0002", "dismiss")):
        _fb(c, h, sid, pid, ev)
    r = c.get(f"/recs/sessions/{sid}", headers=h)
    assert r.status_code == 200 and r.json()["active"] is True
    assert c.delete(f"/recs/sessions/{sid}", headers=h).status_code == 204
    after = c.get(f"/recs/sessions/{sid}", headers=h).json()
    assert (after["active"], after["signals"], after["chips"]) == (False, 0, [])
    assert _q(c, "select count(*) from rec_feedback")[0][0] == 3  # журнал не трогаем
    t = _fb(c, h, sid, "pid0003", "open")  # новые реакции после сброса учитываются
    assert t["signals"] == 1


def test_foreign_session_404(c, h):
    sid = str(uuid.uuid4())
    _search(c, h, sid)
    for pid, ev in (("pid0005", "shortlist"), ("pid0001", "dismiss"), ("pid0002", "dismiss")):
        _fb(c, h, sid, pid, ev)
    h2 = _employer(c, "other@x.ru", name="Other Co")
    for method in ("get", "delete"):
        r = getattr(c, method)(f"/recs/sessions/{sid}", headers=h2)
        assert r.status_code == 404 and r.json()["code"] == "rec_session_not_found"
    assert c.get(f"/recs/sessions/{uuid.uuid4()}", headers=h).status_code == 404
    # чужой session_id в поиске не подстраивает выдачу
    out = _search(c, h2, sid)
    assert out.get("tuning") is None or out["tuning"]["active"] is False
    assert c.get(f"/recs/sessions/{sid}", headers=h).json()["active"] is True


def test_session_permissions(c, h):
    sid = str(uuid.uuid4())
    _search(c, h, sid)
    assert c.get(f"/recs/sessions/{sid}").status_code == 401
    cand_h = _user(c, "cand@x.ru", "candidate")
    assert c.get(f"/recs/sessions/{sid}", headers=cand_h).status_code == 403
    assert c.delete(f"/recs/sessions/{sid}", headers=cand_h).status_code == 403
