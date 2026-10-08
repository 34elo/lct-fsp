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
    "relocation", "search_status", "match", "updated_at", "categories", "strength",
    "is_shortlisted", "interested_you",
}  # fmt: skip
TEST_GRADE = {"junior": "junior", "middle": "middle", "senior": "senior", "lead": "senior"}


def _grade(con, uid, profession, grade, *, valid_until="2999-01-01 00:00:00"):
    """Действующий грейд из теста (таблица `grades`, blocks.md §4.2) — без него кандидат скрыт."""
    con.execute(
        "insert into grades (candidate_id, profession, grade, theta, band_position, theta_by_type,"
        " integrity, needs_confirmation, low_confidence, source, confirmed_at, valid_until,"
        " next_change_at, updated_at) values (?,?,?,0.5,0.5,'{}',1.0,0,0,'seed',?,?,?,?)",
        (uid, profession, grade, NOW, valid_until, NOW, NOW),
    )


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


def _cand(c, n, skills=(), *, tested=True, **kw):
    """Анкета + рёбра навыков: skills = [(slug, confidence, level, sources)].

    `tested` — грейд из теста по `primary_role` × `grade` анкеты (как seed-грейды до Т2)."""
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
        con.execute(
            "insert into consents (user_id, type, version, granted_at) values (?,?,?,?)",
            (uid, "profile_publication", "2025-09-01", NOW),
        )
        if tested and row["primary_role"] and row["grade"]:
            _grade(con, uid, row["primary_role"], TEST_GRADE[row["grade"]])
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


def test_candidate_without_profile_publication_is_hidden_and_revoke_hides(c, market):
    """E20-11: без согласия `profile_publication` кандидата нет в выдаче; отзыв скрывает."""
    uid = _cand(c, 25, [("python", 0.5, 2, ["github"])])
    assert "pid0025" in _pids(_search(c, market, limit=100))
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update consents set revoked_at=? where user_id=? and type='profile_publication'",
            (NOW, uid),
        )
    assert "pid0025" not in _pids(_search(c, market, limit=100))
    with sqlite3.connect(c.db) as con:
        con.execute("delete from consents where user_id=?", (uid,))
    assert "pid0025" not in _pids(_search(c, market, limit=100))


def test_candidate_without_test_grade_is_hidden(c, market):
    """E23-1 (ADR-018): резюме без теста не даёт категории — в выдаче и карточке кандидата нет;
    истёкший грейд тоже скрывает."""
    _cand(c, 26, [("python", 0.9, 4, ["resume"])], tested=False)
    assert "pid0026" not in _pids(_search(c, market, limit=100))
    assert _card(c, market, "pid0026").status_code == 404
    uid = _cand(c, 27, [("python", 0.9, 4, ["resume"])], tested=False)
    with sqlite3.connect(c.db) as con:
        _grade(con, uid, "backend", "middle", valid_until="2000-01-01 00:00:00")
    assert "pid0027" not in _pids(_search(c, market, limit=100))
    with sqlite3.connect(c.db) as con:
        con.execute("update grades set valid_until='2999-01-01 00:00:00' where candidate_id=?",
                    (uid,))  # fmt: skip
    assert "pid0027" in _pids(_search(c, market, limit=100))  # ключ кеша сменился
    assert _card(c, market, "pid0027").status_code == 200


def test_category_filter_and_card_fields(c, market):
    """E23-1: фильтр по категории (профессия × грейд из теста), поля `categories` и
    `claimed_vs_confirmed` в карточке."""
    uid = _cand(c, 40, [("python", 0.6, 3, ["test"])], grade="middle")
    with sqlite3.connect(c.db) as con:
        _grade(con, uid, "ml", "junior")
    cat = {"profession": "backend", "grade": "senior"}
    assert _pids(_search(c, market, category=cat, sort="trust")) == ["pid0001"]
    r = _search(c, market, category={"profession": "ml", "grade": "junior"})
    assert _pids(r) == ["pid0040"]
    assert r.json()["items"][0]["categories"] == [
        {"profession": "backend", "grade": "middle"}, {"profession": "ml", "grade": "junior"},
    ]  # fmt: skip
    assert _pids(_search(c, market, category={"profession": "ml", "grade": "senior"})) == []
    assert _search(c, market, category={"profession": "ml", "grade": "lead"}).status_code == 422
    full = _card(c, market, "pid0040").json()
    assert [x["profession"] for x in full["categories"]] == ["backend", "ml"]
    cvc = {x["profession"]: x for x in full["claimed_vs_confirmed"]}
    assert cvc["backend"]["status"] == "confirmed" and cvc["ml"]["confirmed_grade"] == "junior"
    over = _cand(c, 41, [("python", 0.6, 3, ["test"])], grade="senior", tested=False)
    with sqlite3.connect(c.db) as con:
        _grade(con, over, "backend", "junior")
    (row,) = _card(c, market, "pid0041").json()["claimed_vs_confirmed"]
    assert (row["resume_grade"], row["confirmed_grade"], row["status"]) == (
        "senior", "junior", "overclaimed",
    )  # fmt: skip


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


def test_mutual_sort_is_default_with_vacancy_and_shows_interest(c, market):
    body = {
        "title": "Backend", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python", "required": True, "min_level": 3}],
    }  # fmt: skip
    vid = c.post("/vacancies", json=body, headers=_hdr(market)).json()["id"]
    default = _search(c, market, vacancy_id=vid).json()["items"]
    mutual_ = _search(c, market, vacancy_id=vid, sort="mutual").json()["items"]
    assert [i["pseudo_id"] for i in default] == [i["pseudo_id"] for i in mutual_]
    matched = [i for i in mutual_ if i["match"]]
    assert matched and all(i["match"]["interest"] in ("low", "medium", "high") for i in matched)
    assert mutual_[-1]["match"] is None  # не прошёл жёсткие фильтры — после подходящих
    only = _search(c, market, vacancy_id=vid, sort="match").json()["items"]
    assert all(i["match"]["interest"] for i in only if i["match"])
    # без вакансии mutual = match
    a = _pids(_search(c, market, filters={"skills_must": [{"slug": "python"}]}, sort="mutual"))
    b = _pids(_search(c, market, filters={"skills_must": [{"slug": "python"}]}, sort="match"))
    assert a == b


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
            con.execute(
                "insert into consents (user_id, type, version, granted_at) values (?,?,?,?)",
                (row["user_id"], "profile_publication", "2025-09-01", NOW),
            )
            _grade(con, row["user_id"], "backend", "senior")
    t = time.perf_counter()
    r = _search(c, market, sort="trust", filters={"skills_must": [{"slug": "python"}]})
    assert r.status_code == 200 and r.json()["total"] >= 500
    assert time.perf_counter() - t < 0.3


# --- E7-4: карточка и журнал просмотров -------------------------------------------------


def _card(c, h, pid, **q):
    return c.get(f"/candidates/{pid}/card", params=q, headers=_hdr(h))


def _views(c):
    with sqlite3.connect(c.db) as con:
        return con.execute("select company_id, source, vacancy_id from profile_views").fetchall()


def test_card_full_is_anonymous_and_logs_view(c, market):
    uid = _cand(c, 40, [("python", 0.8, 3, ["github"]), ("fastapi", 0.3, 1, ["resume"])])
    with sqlite3.connect(c.db) as con:
        con.execute("update candidates set visibility=? where user_id=?",
                    (json.dumps({"companies": False}), uid))  # fmt: skip
        con.execute("update users set id=id where 0")  # no-op: user row не нужен для карточки
        con.execute(
            "insert into experience (id, candidate_id, company, title, start_date, end_date,"
            " skill_ids, is_commercial, source) values (?,?,?,?,?,?,?,1,'resume')",
            (uuid.uuid4().hex, uid, "Секретная Компания", "Разработчик", "2020-01-01",
             "2021-01-01", json.dumps([c.skills["python"]])),
        )  # fmt: skip
    r = _card(c, market, "pid0040")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == CARD_FIELDS | {
        "skills", "grade_info", "experience", "offers_from_you", "claimed_vs_confirmed",
    }  # fmt: skip
    assert body["pseudonym"] == "Backend #40" and body["offers_from_you"] == []
    assert [s["skill"]["slug"] for s in body["skills"]] == ["python", "fastapi"]
    assert body["skills"][1]["claimed_only"] is False or body["skills"][1]["level"] == 1
    (e,) = body["experience"]
    assert e["company"] is None and e["months"] == 12 and e["skills"] == ["python"]
    text = json.dumps(body, ensure_ascii=False)
    assert "Секретная" not in text and "user_id" not in text
    assert uid not in text and uid.replace("-", "") not in text
    assert len(_views(c)) == 1 and _views(c)[0][1] == "direct"
    _card(c, market, "pid0040", source="search")
    assert len(_views(c)) == 2


def test_card_shows_company_only_when_allowed(c, market):
    uid = _cand(c, 41, [("python", 0.8, 3, ["github"])])
    with sqlite3.connect(c.db) as con:
        con.execute("update candidates set visibility=? where user_id=?",
                    (json.dumps({"companies": True}), uid))  # fmt: skip
        con.execute(
            "insert into experience (id, candidate_id, company, title, start_date, skill_ids,"
            " is_commercial, source) values (?,?,?,?,?,'[]',1,'resume')",
            (uuid.uuid4().hex, uid, "Открытая Компания", "Dev", "2023-01-01"),
        )
    assert _card(c, market, "pid0041").json()["experience"][0]["company"] == "Открытая Компания"


def test_card_applies_candidate_privacy_settings(c, market):
    """E36-4: умолчания (компании, регион видны) и переключатели region/companies/fsp."""
    uid = _cand(c, 42, [("python", 0.8, 3, ["github"])], city="Казань")
    with sqlite3.connect(c.db) as con:
        con.execute(
            "insert into experience (id, candidate_id, company, title, start_date, skill_ids,"
            " is_commercial, source) values (?,?,?,?,?,'[]',1,'resume')",
            (uuid.uuid4().hex, uid, "Открытая Компания", "Dev", "2023-01-01"),
        )
    full = _card(c, market, "pid0042").json()  # анкета с пустой visibility = умолчания
    assert full["city"] == "Казань" and full["experience"][0]["company"] == "Открытая Компания"
    assert "full_name" not in full and "contacts" not in json.dumps(full)
    with sqlite3.connect(c.db) as con:
        hide = json.dumps({"region": False, "companies": False, "fsp": False})
        con.execute("update candidates set visibility=? where user_id=?", (hide, uid))
    hidden = _card(c, market, "pid0042").json()
    assert hidden["city"] is None and hidden["experience"][0]["company"] is None
    assert hidden["fsp_highlights"] == []
    assert _search(c, market).json()["items"] and all(
        i["city"] is None for i in _search(c, market).json()["items"] if i["pseudo_id"] == "pid0042"
    )


def test_card_hidden_and_foreign_resources_404(c, market):
    _cand(c, 42, [("python", 0.5, 2, ["github"])], stoplist_company_ids=[market["company_id"]])
    assert _card(c, market, "pid0004").status_code == 404  # dnd
    assert _card(c, market, "pid0042").status_code == 404  # стоп-лист компании
    assert _card(c, market, "nope").status_code == 404
    other = _employer(c, "o2@x.ru", name="Other")
    vac = c.post("/vacancies", json={
        "title": "Dev", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python"}],
    }, headers=_hdr(other)).json()  # fmt: skip
    assert _card(c, market, "pid0001", vacancy_id=vac["id"]).status_code == 404
    assert _card(c, market, "pid0001", vacancy_id=str(uuid.uuid4())).status_code == 404
    assert _views(c) == []  # неудачные запросы просмотр не пишут
    reg = c.post("/auth/register", json={"email": "cc@x.ru", "password": PWD, "role": "candidate"})
    cand_h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert c.get("/candidates/pid0001/card", headers=cand_h).status_code == 403


def test_card_with_vacancy_has_match_and_candidate_sees_aggregates(c, market):
    vac = c.post("/vacancies", json={
        "title": "Dev", "role": "backend", "grade_min": "junior", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python"}],
    }, headers=_hdr(market)).json()  # fmt: skip
    r = _card(c, market, "pid0001", vacancy_id=vac["id"], source="match")
    assert r.status_code == 200 and r.json()["match"]["score"] > 0
    assert _views(c)[0][1:] == ("match", vac["id"].replace("-", ""))


def test_my_views_aggregates_without_company_names(c, market):
    reg = c.post("/auth/register", json={"email": "cv@x.ru", "password": PWD,
                                         "role": "candidate"}).json()  # fmt: skip
    h = {"Authorization": f"Bearer {reg['access_token']}"}
    me = c.get("/me", headers=h).json()
    uid = me.get("id") or me.get("user_id")
    with sqlite3.connect(c.db) as con:
        pid = c.get("/candidates/me/profile", headers=h)  # создаёт анкету
        con.execute("update candidates set primary_role='backend', pseudo_id='pidself' "
                    "where user_id=?", (uid.replace("-", ""),))  # fmt: skip
        con.execute(
            "insert into consents (user_id, type, version, granted_at) values (?,?,?,?)",
            (uid.replace("-", ""), "profile_publication", "2025-09-01", NOW),
        )
        _grade(con, uid.replace("-", ""), "backend", "middle")
    for _ in range(2):
        assert _card(c, market, "pidself").status_code == 200
    other = _employer(c, "o3@x.ru", name="Other3")
    assert _card(c, other, "pidself").status_code == 200
    r = c.get("/candidates/me/views", headers=h)
    assert r.status_code == 200 and pid.status_code == 200
    body = r.json()
    assert body["total_30d"] == 3 and body["companies_30d"] == 2
    assert sum(d["count"] for d in body["by_day"]) == 3
    assert "Acme" not in json.dumps(body)
    assert c.get("/candidates/me/views", headers=_hdr(market)).status_code == 403


def _similar(c, h, pid, **q):
    return c.get(f"/candidates/{pid}/similar", params=q, headers=_hdr(h))


def test_similar_ranks_by_overlap_and_is_anonymous(c, market):
    _cand(c, 10, [("python", 0.9, 4, ["github"]), ("fastapi", 0.6, 3, ["github"])])
    r = _similar(c, market, "pid0001")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    pids = [i["pseudo_id"] for i in items]
    assert pids[0] == "pid0010" and items[0]["similarity"] == pytest.approx(1.0)
    assert "pid0001" not in pids  # сам кандидат исключён
    assert "pid0004" not in pids  # dnd скрыт
    assert items[0]["common_skills"] == ["Fastapi", "Python"]
    assert set(items[0]) == CARD_FIELDS | {"similarity", "common_skills"}
    assert [i["similarity"] for i in items] == sorted(
        (i["similarity"] for i in items), reverse=True
    )
    assert _similar(c, market, "pid0001", limit=1).json()["items"][0]["pseudo_id"] == "pid0010"


def test_similar_hidden_foreign_and_role_404_403(c, market):
    _cand(c, 42, [("python", 0.5, 2, ["github"])], stoplist_company_ids=[market["company_id"]])
    assert _similar(c, market, "pid0004").status_code == 404  # dnd
    assert _similar(c, market, "pid0042").status_code == 404  # стоп-лист
    assert _similar(c, market, "nope").status_code == 404
    other = _employer(c, "o3@x.ru", name="Other")
    _cand(c, 43, [("python", 0.9, 4, ["github"])], stoplist_company_ids=[market["company_id"]])
    pids = [i["pseudo_id"] for i in _similar(c, other, "pid0001").json()["items"]]
    assert "pid0043" in pids  # у другой компании не скрыт
    assert "pid0043" not in [i["pseudo_id"] for i in _similar(c, market, "pid0001").json()["items"]]
    reg = c.post("/auth/register", json={"email": "cs@x.ru", "password": PWD, "role": "candidate"})
    ch = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert c.get("/candidates/pid0001/similar", headers=ch).status_code == 403


def test_similarity_formula():
    from app.matching.similar import similarity, skill_overlap

    a, b = {"x": 0.8, "y": 0.4}, {"x": 0.4, "z": 0.4}
    assert skill_overlap(a, b) == pytest.approx(0.4 / 1.6)
    assert skill_overlap({}, {}) == 0.0
    assert similarity(a, b, None, [1.0]) == pytest.approx(0.25)  # нет вектора → только навыки
    assert similarity(a, a, [1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert similarity(a, a, [1.0, 0.0], [-1.0, 0.0]) == pytest.approx(0.7)


def test_strength_and_rank_in_category(c, market):
    """E23-2: в категории порядок по rank, у карточки сила и топ-3 слагаемых; без ФСП — F = 0."""
    a = _cand(c, 50, [("python", 0.8, 3, ["test"])], grade="middle")
    b = _cand(c, 51, [("python", 0.8, 3, ["test", "fsp"])], grade="middle")
    d = _cand(c, 52, [("python", 0.8, 3, ["test"])], grade="middle")
    with sqlite3.connect(c.db) as con:
        con.execute("update grades set band_position=0.9 where candidate_id=?", (a,))
        con.execute("update grades set band_position=0.2 where candidate_id=?", (b,))
        con.execute("update grades set band_position=0.2, integrity=0.3 where candidate_id=?", (d,))
    cat = {"profession": "backend", "grade": "middle"}
    r = _search(c, market, category=cat, filters={"skills_nice": ["python"]})
    items = {i["pseudo_id"]: i for i in r.json()["items"]}
    assert {"pid0050", "pid0051", "pid0052"} <= set(items)
    sa, sb, sd = (items[k]["strength"] for k in ("pid0050", "pid0051", "pid0052"))
    assert sa["value"] > sb["value"] > sd["value"]  # T=0.9 > ФСП при T=0.2 > штраф честности
    assert sa["rank"] == round(0.6 * 0.8 + 0.4 * sa["value"], 6)
    assert len(sa["top"]) == 3 and sa["top"][0]["code"] == "T"
    assert "F" not in [x["code"] for x in sa["top"]]  # без ФСП слагаемого нет, штрафа тоже
    order = [i["pseudo_id"] for i in r.json()["items"]]
    assert order.index("pid0050") < order.index("pid0051") < order.index("pid0052")
    plain = _search(c, market, filters={"skills_nice": ["python"]}).json()["items"][0]
    assert plain["strength"]["rank"] is None  # без категории rank не считается


def test_candidate_interest_boost_only_for_marked_company(c):
    """E33-6: отметка кандидата поднимает его только в выдаче этой компании."""
    a = _employer(c, "a@x.ru", name="Acme Labs")
    b = _employer(c, "b@x.ru", name="Beta Labs")
    sk = [("python", 0.8, 3, ["github"])]
    u1 = _cand(c, 1, sk)
    u2 = _cand(c, 2, sk)
    f = {"skills_must": [{"slug": "python"}]}
    base = _pids(_search(c, a, filters=f, sort="match"))
    assert sorted(base) == ["pid0001", "pid0002"]
    low = base[-1]
    low_uid = u1 if low == "pid0001" else u2
    with sqlite3.connect(c.db) as con:
        con.execute(
            "insert into candidate_interests (candidate_id, company_id, created_at) values (?,?,?)",
            (low_uid, a["company_id"].replace("-", ""), NOW),
        )
    r = _search(c, a, filters=f, sort="match")
    assert _pids(r)[0] == low  # в своей компании поднялся
    assert {i["pseudo_id"]: i["interested_you"] for i in r.json()["items"]} == {
        base[0]: False, low: True,
    }  # fmt: skip
    rb = _search(c, b, filters=f, sort="match")
    assert _pids(rb) == base  # у другой компании порядок прежний
    assert not any(i["interested_you"] for i in rb.json()["items"])
