"""Правиловый парсер текстового запроса и POST /search/parse (ml.md §7, E7-5)."""

import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from app.matching.query_parser import parse_query
from app.taxonomy.loader import load_taxonomy, norm_alias
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"


@pytest.fixture(scope="module")
def forms() -> dict[str, str]:
    data = load_taxonomy(CORE.parents[1] / "data" / "taxonomy")
    out: dict[str, set[str]] = {}
    for s in data.skills:
        for f in (s.slug, s.name, *s.aliases):
            out.setdefault(norm_alias(f), set()).add(s.slug)
    return {f: next(iter(v)) for f, v in out.items() if len(v) == 1}


def _must(r):
    return [s.slug for s in r.filters.skills_must or []]


def test_main_example_from_docs(forms):
    r = parse_query("найди middle python с FastAPI, удалённо, до 250к", forms)
    f = r.filters
    assert (f.grade_min, f.grade_max) == ("middle", "middle")
    assert _must(r) == ["python", "fastapi"]
    assert f.formats == ["remote"] and f.salary_max == 250_000
    assert f.semantic_text is None and r.unparsed == [] and r.refining is False
    assert {c.source for c in r.chips} == {"rule"}
    assert {c.key for c in r.chips} == {"grade_min", "skills_must", "formats", "salary_max"}


@pytest.mark.parametrize(
    ("text", "salary"),
    [
        ("до 220 тыс", 220_000),
        ("до 220 тысяч рублей", 220_000),
        ("200-250к", 250_000),
        ("200–250 тыс", 250_000),
        ("от 150 до 250к", 250_000),
        ("до 250 000", 250_000),
        ("бюджет 300000 ₽", 300_000),
        ("нужен 300000", None),  # без «до» и единицы — не гадаем
        ("до 1,5 млн", 1_500_000),
        ("250 т.р.", 250_000),
        ("до 3 лет опыта", None),
        ("python 3-5 лет", None),
    ],
)
def test_money(forms, text, salary):
    assert parse_query(text, forms).filters.salary_max == salary


def test_money_floor_is_not_a_filter(forms):
    r = parse_query("от 150 000", forms)
    assert r.filters.salary_max is None and r.unparsed == ["от 150 000"]


@pytest.mark.parametrize(
    ("text", "lo", "hi"),
    [
        ("мидл разработчик", "middle", "middle"),
        ("Middle+ java", "middle_plus", "middle_plus"),
        ("джун+", "junior_plus", "junior_plus"),
        ("сеньор", "senior", "senior"),
        ("senior+", "senior", "lead"),
        ("тимлид", "lead", "lead"),
        ("middle-senior", "middle", "senior"),
        ("от middle до senior", "middle", "senior"),
        ("стажёр", "intern", "intern"),
    ],
)
def test_grades(forms, text, lo, hi):
    f = parse_query(text, forms).filters
    assert (f.grade_min, f.grade_max) == (lo, hi)


def test_formats_roles_cities_flags(forms):
    f = parse_query(
        "бэкенд на Django в Москве или Питере, гибрид или удаленка, готов к релокации, "
        "из ФСП, активно ищет",
        forms,
    ).filters
    assert f.roles == ["backend"] and _skills(f) == ["django"]
    assert f.cities == ["Москва", "Санкт-Петербург"]
    assert f.formats == ["hybrid", "remote"]
    assert f.relocation_ok and f.fsp_only and f.active_only


def _skills(f):
    return [s.slug for s in f.skills_must or []]


def test_role_words_do_not_become_skills(forms):
    f = parse_query("ML-инженер, devops, frontend", forms).filters
    assert f.roles == ["ml", "devops", "frontend"]
    assert not f.skills_must


def test_nice_to_have_split_from_must(forms):
    f = parse_query("python, желательно kafka и docker", forms).filters
    assert _skills(f) == ["python"] and f.skills_nice == ["kafka", "docker"]
    f = parse_query("python, Spring Boot будет плюсом", forms).filters
    assert _skills(f) == ["python"] and f.skills_nice == ["spring-boot"]


def test_internship_sets_employment_and_grade(forms):
    f = parse_query("стажёр аналитик sql", forms).filters
    assert f.employment_types == ["internship"] and f.grade_min == "intern"
    assert f.roles == ["analyst"] and _skills(f) == ["sql"]


def test_ambiguous_short_words_are_not_skills(forms):
    # «го» и «си» по-русски — частицы; «C++» — навык
    assert _skills(parse_query("нужен го и си", forms.copy()).filters) == []
    assert _skills(parse_query("C++ разработчик", forms).filters) == ["cpp"]


def test_semantic_remainder_and_chips(forms):
    r = parse_query("senior python, высоконагруженный API", forms)
    assert r.filters.semantic_text == "высоконагруженный api"
    chip = next(c for c in r.chips if c.key == "skills_must")
    assert chip.value == {"slug": "python"} and chip.label == "Навык: python"
    assert next(c for c in r.chips if c.key == "semantic_text").confidence <= 0.5


def test_empty_and_garbage(forms):
    r = parse_query("найди", forms)
    assert r.filters.model_dump(exclude_none=True) == {} and r.chips == []
    assert parse_query("!!! ??? ...", forms).chips == []


def test_deterministic(forms):
    q = "найди middle python с FastAPI, удалённо, до 250к"
    assert parse_query(q, forms) == parse_query(q, forms)


# --- эндпоинт ----------------------------------------------------------------------------------


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "p.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    with sqlite3.connect(db) as con:
        for slug, name, aliases in (
            ("python", "Python", ["питон"]),
            ("fastapi", "FastAPI", ["фастапи"]),
        ):
            sid = uuid.uuid4().hex
            con.execute(
                "insert into skills (id, slug, name, kind, status, source, support_candidates,"
                " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
                (sid, slug, name, "hard", "active", "seed"),
            )
            for a in aliases:
                con.execute(
                    "insert into skill_aliases (alias_norm, skill_id, source) values (?,?,?)",
                    (a, sid, "seed"),
                )
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        yield client


def _reg(c, email, role):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_endpoint_parses_with_db_taxonomy(c):
    h = _reg(c, "e@x.ru", "employer")
    r = c.post("/search/parse", json={"text": "мидл питон с фастапи, удалённо, до 250к"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filters"]["skills_must"] == [
        {"slug": "python", "min_level": None},
        {"slug": "fastapi", "min_level": None},
    ]
    assert body["filters"]["salary_max"] == 250_000 and body["refining"] is False
    labels = {ch["label"] for ch in body["chips"]}
    assert {"Навык: Python", "Навык: FastAPI", "Грейд: Middle"} <= labels


def test_endpoint_permissions_and_validation(c):
    assert c.post("/search/parse", json={"text": "python"}).status_code == 401
    cand = _reg(c, "k@x.ru", "candidate")
    assert c.post("/search/parse", json={"text": "python"}, headers=cand).status_code == 403
    h = _reg(c, "e@x.ru", "employer")
    assert c.post("/search/parse", json={"text": ""}, headers=h).status_code == 422
    assert c.post("/search/parse", json={"text": "x" * 501}, headers=h).status_code == 422


# --- LLM-уточнение и слияние (E7-6) -------------------------------------------------------------


def _llm_client(handler, redis=None):
    import httpx
    from app.matching.query_llm import QueryLlmClient

    return QueryLlmClient(
        "http://ml", redis=redis, transport=httpx.MockTransport(handler), timeout=1.0
    )


def _llm_reply(**filters):
    return {"filters": filters, "chips": [], "unparsed": [], "refining": True}


def test_merge_rules_win_llm_adds(forms):
    from app.matching.query_llm import merge
    from fsp_contracts.ml import ParsedQuery

    names = {"python": "Python", "fastapi": "FastAPI"}
    rule = parse_query("мидл python, до 250к", forms, names)
    llm = ParsedQuery.model_validate(
        _llm_reply(
            roles=["backend", "devops"],
            salary_max=300_000,
            grade_min="senior",
            formats=["remote"],
            skills_must=[{"slug": "fastapi"}, {"slug": "python"}, {"slug": "выдуманный"}],
            semantic_text="API для финтеха",
        )
    )
    r = merge(rule, llm, forms, names)
    f = r.filters
    assert r.refining and f.salary_max == 250_000 and f.grade_min == "middle"
    assert f.roles == ["backend", "devops"] and f.formats == ["remote"]
    assert [s.slug for s in f.skills_must] == ["python", "fastapi"]  # неизвестный отброшен
    assert f.semantic_text == "API для финтеха"
    labels = {c.label for c in r.chips}
    assert "Бюджет: до 300 000 ₽?" in labels and "Грейд от Senior?" in labels
    assert "Бюджет: до 250 000 ₽" in labels and "Навык: FastAPI" in labels


def test_merge_without_llm_is_rule(forms):
    from app.matching.query_llm import merge

    rule = parse_query("python", forms)
    assert merge(rule, None, forms, {}) is rule


async def test_client_degrades_and_caches(forms):
    import fakeredis
    import httpx

    rule = parse_query("питон", forms)
    calls = []

    def boom(req):
        calls.append(1)
        return httpx.Response(503, json={"code": "ml_unavailable"})

    assert await _llm_client(boom).parse("питон", rule, 1) is None

    def bad(req):
        return httpx.Response(200, json={"filters": {"roles": ["nonsense"]}})

    assert await _llm_client(bad).parse("питон", rule, 1) is None

    def down(req):
        raise httpx.ConnectError("no route")

    assert await _llm_client(down).parse("питон", rule, 1) is None

    redis = fakeredis.FakeAsyncRedis()
    n = []

    def ok(req):
        n.append(1)
        return httpx.Response(200, json=_llm_reply(roles=["backend"]))

    cl = _llm_client(ok, redis)
    first = await cl.parse("Питон ", rule, 7)
    second = await cl.parse("питон", rule, 7)  # тот же нормализованный текст — из кеша
    assert first == second and len(n) == 1
    assert await redis.ttl(next(iter(await redis.keys("c:qparse:7:*")))) > 0
    await cl.parse("питон", rule, 8)  # другая версия справочника — новый ключ
    assert len(n) == 2


def test_endpoint_merges_llm_and_degrades(c):
    import httpx

    h = _reg(c, "e@x.ru", "employer")
    seen = []

    def handler(req):
        seen.append(req.read())
        return httpx.Response(200, json=_llm_reply(roles=["backend"], semantic_text="финтех"))

    c.app.state.query_llm = _llm_client(handler)
    r = c.post("/search/parse", json={"text": "питон, до 250к"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refining"] is True and body["filters"]["roles"] == ["backend"]
    assert body["filters"]["salary_max"] == 250_000 and body["filters"]["semantic_text"] == "финтех"
    assert b"rule_hint" in seen[0]

    def broken(req):
        return httpx.Response(500)

    c.app.state.query_llm = _llm_client(broken)
    r = c.post("/search/parse", json={"text": "питон, до 260к"}, headers=h)
    assert r.status_code == 200 and r.json()["refining"] is False
    assert r.json()["filters"]["salary_max"] == 260_000
