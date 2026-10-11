"""Тесты логирования показов и реакций."""

import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import create_engine, inspect

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
NOW = datetime.now(UTC).isoformat(sep=" ")


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "c.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
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
    return h, co["id"].replace("-", "")


def _cand(c, n):
    uid = uuid.uuid4().hex
    row = dict(
        pseudonym=f"Backend #{n}", pseudo_id=f"pid{n:04d}", primary_role="backend",
        grade="middle", grade_confidence=0.75, formats=["remote"], employment_types=["full"],
        city="Москва", relocation=False, search_status="open", stoplist_company_ids=[],
        primary_stack=["python"],
    )  # fmt: skip
    cols = ["user_id", "visibility", "updated_at", *row]
    vals = [uid, "{}", NOW, *(json.dumps(v) if isinstance(v, list) else v for v in row.values())]
    with sqlite3.connect(c.db) as con:
        con.execute(
            f"insert into candidates ({','.join(cols)}) values ({','.join('?' * len(cols))})", vals
        )
        con.execute(
            "insert into consents (user_id, type, version, granted_at) values (?,?,?,?)",
            (uid, "profile_publication", "2025-09-01", NOW),
        )
        con.execute(
            "insert into grades (candidate_id, profession, grade, theta, band_position,"
            " theta_by_type, integrity, needs_confirmation, low_confidence, source, confirmed_at,"
            " valid_until, next_change_at, updated_at)"
            " values (?,?,?,0.5,0.5,'{}',1.0,0,0,'seed',?,'2999-01-01 00:00:00',?,?)",
            (uid, "backend", "middle", NOW, NOW, NOW),
        )  # грейд из теста: без него кандидат не виден
    return uid


def _q(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


@pytest.fixture
def market(c):
    h, company_id = _employer(c, "e@x.ru")
    cands = {f"pid{n:04d}": _cand(c, n) for n in (1, 2, 3)}
    return h, company_id, cands


def _search(c, h, **body):
    return c.post("/search/candidates", json=body, headers=h)


def test_search_writes_impressions_with_positions_and_session(c, market):
    h, company_id, cands = market
    sid = str(uuid.uuid4())
    r = _search(c, h, session_id=sid)
    assert r.status_code == 200, r.text
    assert r.json()["session_id"] == sid
    pids = [i["pseudo_id"] for i in r.json()["items"]]
    assert len(pids) == 3

    rows = _q(
        c,
        "select position, candidate_id, session_id, context_type, context_id, company_id,"
        " model_version from impressions order by position",
    )
    assert [x[0] for x in rows] == [1, 2, 3]
    assert [x[1] for x in rows] == [cands[p] for p in pids]
    assert {x[2] for x in rows} == {str(uuid.UUID(sid))}
    assert {(x[3], x[4]) for x in rows} == {("search", "")}
    assert {x[5] for x in rows} == {company_id}


def test_search_generates_session_id_when_absent(c, market):
    h, _, _ = market
    r = _search(c, h)
    sid = r.json()["session_id"]
    assert str(uuid.UUID(sid)) == sid
    assert _q(c, "select count(*) from impressions where session_id=?", sid)[0][0] == 3


def _body(c, event="open"):
    sid, pid = _q(
        c,
        "select i.session_id, c.pseudo_id from impressions i"
        " join candidates c on c.user_id=i.candidate_id limit 1",
    )[0]
    return {"session_id": sid, "candidate_pseudo_id": pid, "event": event}


def test_feedback_is_recorded(c, market):
    h, company_id, cands = market
    _search(c, h)
    imp_id, cand_id, sid = _q(
        c, "select id, candidate_id, session_id from impressions where position=2"
    )[0]
    pid = _q(c, "select pseudo_id from candidates where user_id=?", cand_id)[0][0]
    r = c.post(
        "/recs/feedback",
        json={
            "session_id": sid,
            "candidate_pseudo_id": pid,
            "event": "dismiss",
            "reason": "дорого",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["impression_id"] == imp_id and r.json()["event"] == "dismiss"
    rows = _q(
        c,
        "select impression_id, company_id, session_id, candidate_id, event, reason"
        " from rec_feedback",
    )
    assert rows == [(imp_id, company_id, sid, cand_id, "dismiss", "дорого")]
    # повтор — это новая реакция (журнал событий), на показ не влияет
    assert (
        c.post(
            "/recs/feedback",
            json={"session_id": sid, "candidate_pseudo_id": pid, "event": "open"},
            headers=h,
        ).status_code
        == 200
    )
    assert _q(c, "select count(*) from rec_feedback")[0][0] == 2
    assert _q(c, "select count(*) from impressions")[0][0] == 3


def test_feedback_uses_last_impression_in_session(c, market):
    h, _, _ = market
    sid = str(uuid.uuid4())
    _search(c, h, session_id=sid)
    _search(c, h, session_id=sid)
    body = _body(c)
    r = c.post("/recs/feedback", json=body, headers=h)
    assert r.status_code == 200, r.text
    last = _q(
        c,
        "select max(i.id) from impressions i join candidates c on c.user_id=i.candidate_id"
        " where c.pseudo_id=? and i.session_id=?",
        body["candidate_pseudo_id"],
        body["session_id"],
    )[0][0]
    assert r.json()["impression_id"] == last


def test_feedback_validation(c, market):
    h, _, _ = market
    _search(c, h)
    body = _body(c)
    assert c.post("/recs/feedback", json={**body, "event": "bogus"}, headers=h).status_code == 422
    assert c.post("/recs/feedback", json={**body, "event": "offer"}, headers=h).status_code == 422
    assert _q(c, "select count(*) from rec_feedback")[0][0] == 0


def test_feedback_unknown_impression_404(c, market):
    h, _, _ = market
    body = {"session_id": "nope", "candidate_pseudo_id": "pid0001", "event": "open"}
    r = c.post("/recs/feedback", json=body, headers=h)
    assert r.status_code == 404
    assert r.json()["code"] == "impression_not_found"


def test_feedback_foreign_impression_404(c, market):
    h, _, _ = market
    _search(c, h)
    body = _body(c)
    h2, _ = _employer(c, "other@x.ru", name="Other Co")
    r = c.post("/recs/feedback", json=body, headers=h2)
    assert r.status_code == 404
    assert r.json()["code"] == "impression_not_found"
    assert _q(c, "select count(*) from rec_feedback")[0][0] == 0


def test_feedback_permissions(c, market):
    h, _, _ = market
    _search(c, h)
    body = _body(c)
    assert c.post("/recs/feedback", json=body).status_code == 401
    cand_h = _user(c, "cand@x.ru", "candidate")
    assert c.post("/recs/feedback", json=body, headers=cand_h).status_code == 403
    assert _q(c, "select count(*) from rec_feedback")[0][0] == 0


def test_schema_matches_data_model(c):
    insp = inspect(create_engine(f"sqlite:///{c.db}"))
    assert [x["name"] for x in insp.get_columns("impressions")] == [
        "id", "company_id", "user_id", "session_id", "context_type", "context_id",
        "candidate_id", "position", "score", "features", "model_version", "shown_at",
    ]  # fmt: skip
    assert [x["name"] for x in insp.get_columns("rec_feedback")] == [
        "id", "impression_id", "company_id", "user_id", "session_id", "candidate_id",
        "event", "reason", "created_at",
    ]  # fmt: skip
    idx = {x["name"]: x["column_names"] for x in insp.get_indexes("impressions")}
    assert idx["ix_impressions_company_shown_at"] == ["company_id", "shown_at"]


def test_migration_0023_downgrade(tmp_path):
    db = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{db}"

    def alembic(*a):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-x", f"url={url}", *a],
            cwd=CORE, check=True, capture_output=True,
        )  # fmt: skip

    def tables():
        return set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())

    alembic("upgrade", "head")
    assert {"impressions", "rec_feedback"} <= tables()
    alembic("downgrade", "0022")
    assert not {"impressions", "rec_feedback"} & tables()
    alembic("upgrade", "head")
    assert {"impressions", "rec_feedback"} <= tables()
