"""Поиск кандидатов: фильтры, анонимность DTO, курсор, кеш, права (api.md §2.5, E7-3)."""

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
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
NOW = datetime.now(UTC).isoformat(sep=" ")
CARD_FIELDS = {
    "pseudo_id", "pseudonym", "avatar_seed", "primary_role", "grade", "grade_preliminary",
    "primary_stack", "top_skills", "fsp_highlights", "salary_min", "formats", "city",
    "relocation", "search_status", "match", "updated_at",
}  # fmt: skip


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "s.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    ids = {}
    with sqlite3.connect(db) as con:
        for slug in ("python", "fastapi", "kafka"):
            ids[slug] = uuid.uuid4().hex
            con.execute(
                "insert into skills (id, slug, name, kind, status, source, support_candidates,"
                " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
                (ids[slug], slug, slug.capitalize(), "tech", "active", "seed"),
            )
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db, client.skills = db, ids
        yield client


def _employer(c, email, *, name="Acme Labs"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    co = c.post("/companies", json={"name": name, "inn": INN}, headers=h).json()
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update companies set status='verified' where id=?", (co["id"].replace("-", ""),)
        )
    h["company_id"] = co["id"]
    return h


def _hdr(h):
    return {"Authorization": h["Authorization"]}


def _cand(c, n, skills=(), **kw):
    """Анкета + рёбра навыков: skills = [(slug, confidence, level, sources)]."""
    uid = uuid.uuid4().hex
    row = dict(
        pseudonym=f"Backend #{n}", pseudo_id=f"pid{n:04d}", primary_role="backend", grade="middle",
        grade_confidence=0.75, salary_min=None, formats=["remote"], employment_types=["full"],
        city="Москва", relocation=False, search_status="open", stoplist_company_ids=[],
        primary_stack=["python"],
    )  # fmt: skip
    row.update(kw)
    cols = ["user_id", "visibility", "updated_at", *row]
    vals = [uid, "{}", NOW, *(json.dumps(v) if isinstance(v, list) else v for v in row.values())]
    with sqlite3.connect(c.db) as con:
        con.execute(
            f"insert into candidates ({','.join(cols)}) values ({','.join('?' * len(cols))})", vals
        )
        for slug, conf, level, sources in skills:
            con.execute(
                "insert into candidate_skills (candidate_id, skill_id, confidence, level, sources,"
                " top_evidence, claimed_only) values (?,?,?,?,?,'[]',0)",
                (uid, c.skills[slug], conf, level, json.dumps(sources)),
            )
    return uid


def _search(c, h, **body):
    return c.post("/search/candidates", json=body, headers=_hdr(h))


def _pids(r):
    assert r.status_code == 200, r.text
    return [i["pseudo_id"] for i in r.json()["items"]]


@pytest.fixture
def market(c):
    h = _employer(c, "e@x.ru")
    _cand(c, 1, [("python", 0.9, 4, ["github", "test"]), ("fastapi", 0.6, 3, ["github"])],
          grade="senior", salary_min=300_000)  # fmt: skip
    _cand(c, 2, [("python", 0.5, 2, ["github"]), ("kafka", 0.5, 2, ["resume"])],
          grade="junior", city="Казань", relocation=True, formats=["office", "hybrid"])  # fmt: skip
    _cand(c, 3, [("python", 0.7, 3, ["test"])], primary_role="frontend", search_status="active",
          active_until="2999-01-01 00:00:00")  # fmt: skip
    _cand(c, 4, [("python", 0.99, 4, ["github"])], search_status="dnd")
    return h


def test_card_is_anonymous_and_complete(c, market):
    r = _search(c, market, sort="trust")
    assert r.status_code == 200
    body = r.json()
    assert _pids(r) == ["pid0001", "pid0002", "pid0003"]  # dnd скрыт
    assert body["total"] == 3 and body["next_cursor"] is None and uuid.UUID(body["session_id"])
    card = body["items"][0]
    assert set(card) == CARD_FIELDS
    assert card["pseudonym"] == "Backend #1" and card["grade_preliminary"] is False
    assert [s["slug"] for s in card["top_skills"]] == ["python", "fastapi"]
    assert card["top_skills"][0] == {"slug": "python", "name": "Python", "level": 4,
                                     "sources": ["github", "test"]}  # fmt: skip
    text = json.dumps(body)
    assert "user_id" not in text and "@" not in text  # ПДн и идентификаторы пользователя


def test_filters(c, market):
    def q(**f):
        return _pids(_search(c, market, filters=f, sort="trust"))

    assert q(roles=["frontend"]) == ["pid0003"]
    assert q(grade_min="senior") == ["pid0001"]
    assert q(grade_max="junior") == ["pid0002"]
    assert q(formats=["office"]) == ["pid0002"]
    assert q(salary_max=200_000) == ["pid0002", "pid0003"]  # без вилки подходит под любой бюджет
    assert q(cities=["казань"]) == ["pid0002"]
    assert q(cities=["Санкт-Петербург"]) == ["pid0002"]  # готов к релокации
    assert q(relocation_ok=True) == ["pid0002"]
    assert q(active_only=True) == ["pid0003"]
    assert q(skills_must=[{"slug": "python", "min_level": 3}]) == ["pid0001", "pid0003"]
    assert q(skills_must=[{"slug": "python"}, {"slug": "kafka"}]) == ["pid0002"]
    assert q(skills_must=[{"slug": "python"}], min_trust=4) == ["pid0001"]
    assert q(skills_must=[{"slug": "nope"}]) == []
    assert q(fsp_only=True) == []


def test_sort_match_without_vacancy_uses_requested_skills(c, market):
    f = {"skills_must": [{"slug": "python"}], "skills_nice": ["kafka"]}
    assert _pids(_search(c, market, filters=f, sort="match"))[0] == "pid0001"
    f = {"skills_nice": ["kafka"]}
    assert _pids(_search(c, market, filters=f, sort="match"))[0] == "pid0002"


def test_cursor_pagination_is_stable(c, market):
    for i in range(10, 17):
        _cand(c, i, [("python", 0.1 * (i - 9), 2, ["github"])])
    full = _pids(_search(c, market, sort="trust", limit=100))
    assert len(full) == 10
    seen, cursor = [], None
    while True:
        r = _search(c, market, sort="trust", limit=4, cursor=cursor)
        seen += _pids(r)
        cursor = r.json()["next_cursor"]
        if cursor is None:
            break
    assert seen == full and len(set(seen)) == 10
    assert (
        _pids(_search(c, market, sort="fresh", limit=3))
        and _search(c, market, sort="match", cursor="мусор").status_code == 200
    )  # битый курсор = первая страница


def test_stoplist_hides_candidate_from_that_company(c, market):
    other = _employer(c, "o@x.ru", name="Other")
    _cand(c, 20, [("python", 0.5, 2, ["github"])], stoplist_company_ids=[market["company_id"]])
    assert "pid0020" not in _pids(_search(c, market, limit=100))
    assert "pid0020" in _pids(_search(c, other, limit=100))


def test_fsp_highlights_and_filters(c, market):
    uid = _cand(c, 30, [("python", 0.8, 3, ["fsp"])])
    details = json.dumps({"label": "Кубок ФСП, 2 место из 120", "level": "federal", "place": 2,
                          "participants": 120})  # fmt: skip
    today = datetime.now(UTC).date().isoformat()
    with sqlite3.connect(c.db) as con:
        con.execute(
            "insert into evidence (id, candidate_id, skill_id, source, strength, observed_at,"
            " fact_type, fact_id, details, verified, is_active) values (?,?,?,?,?,?,?,?,?,1,1)",
            (uuid.uuid4().hex, uid, c.skills["python"], "fsp", 0.9, today, "fsp_result",
             uuid.uuid4().hex, details),
        )  # fmt: skip
    r = _search(c, market, filters={"fsp_only": True})
    assert _pids(r) == ["pid0030"]
    (h,) = r.json()["items"][0]["fsp_highlights"]
    assert (h["title"], h["place"], h["of"]) == ("Кубок ФСП, 2 место из 120", 2, 120)


def test_vacancy_match_attached_and_foreign_vacancy_404(c, market):
    other = _employer(c, "o@x.ru", name="Other")
    body = {
        "title": "Backend", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python", "required": True, "min_level": 3}],
    }  # fmt: skip
    vid = c.post("/vacancies", json=body, headers=_hdr(market)).json()["id"]
    r = _search(c, market, vacancy_id=vid, sort="match")
    items = r.json()["items"]
    assert {i["pseudo_id"] for i in items if i["match"]} == {"pid0001", "pid0003"}
    assert items[0]["match"]["score"] >= items[1]["match"]["score"] > 0
    assert items[0]["match"]["explanation"]
    assert all(i["match"]["explanation"] for i in items if i["match"])
    assert items[-1]["match"] is None  # junior, вне вилки грейдов вакансии
    assert _search(c, other, vacancy_id=vid).status_code == 404
    assert _search(c, other, vacancy_id=str(uuid.uuid4())).status_code == 404


def test_permissions(c, market):
    assert c.post("/search/candidates", json={}).status_code == 401
    r = c.post("/auth/register", json={"email": "k@x.ru", "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.post("/search/candidates", json={}, headers=h).status_code == 403
    r = c.post("/auth/register", json={"email": "n@x.ru", "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.post("/search/candidates", json={}, headers=h).status_code == 404  # нет компании
    assert _search(c, market, limit=0).status_code == 422
    assert _search(c, market, sort="random").status_code == 422


def test_cache_hit_and_invalidation_by_catalog_version(c, market):
    first = _search(c, market, sort="trust").json()
    with sqlite3.connect(c.db) as con:  # правка без смены версии каталога: страница из кеша
        con.execute("update candidates set pseudonym='Changed' where pseudo_id='pid0001'")
    again = _search(c, market, sort="trust").json()
    assert again["items"] == first["items"]
    assert again["session_id"] != first["session_id"]
    with sqlite3.connect(c.db) as con:  # пересчёт профиля двигает updated_at → новый ключ
        con.execute(
            "update candidates set updated_at=? where pseudo_id='pid0001'",
            (datetime.now(UTC).replace(year=2099).isoformat(sep=" "),),
        )
    fresh = _search(c, market, sort="trust").json()
    assert fresh["items"][0]["pseudonym"] == "Changed"
    kept = _search(c, market, sort="trust", session_id=first["session_id"]).json()
    assert kept["session_id"] == first["session_id"]


def test_speed_on_500_candidates(c, market):
    import time

    with sqlite3.connect(c.db) as con:
        base = con.execute("select * from candidates where pseudo_id='pid0001'").fetchone()
        cols = [d[0] for d in con.execute("select * from candidates limit 1").description]
        for i in range(500):
            row = dict(zip(cols, base, strict=True))
            row.update(user_id=uuid.uuid4().hex, pseudo_id=f"bulk{i:04d}", pseudonym=f"B #{i}")
            con.execute(
                f"insert into candidates ({','.join(cols)}) values ({','.join('?' * len(cols))})",
                list(row.values()),
            )
            con.execute(
                "insert into candidate_skills (candidate_id, skill_id, confidence, level, sources,"
                " top_evidence, claimed_only) values (?,?,?,?,'[\"github\"]','[]',0)",
                (row["user_id"], c.skills["python"], 0.3 + (i % 7) / 10, 2),
            )
    t = time.perf_counter()
    r = _search(c, market, sort="trust", filters={"skills_must": [{"slug": "python"}]})
    assert r.status_code == 200 and r.json()["total"] >= 500
    assert time.perf_counter() - t < 0.3
