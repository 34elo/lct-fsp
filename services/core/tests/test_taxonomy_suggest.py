"""Подсказки навыков и профессий: синонимы, опечатки, Java ≠ JavaScript, кеш, права."""

from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from app.taxonomy.models import Role, Skill
from fastapi.testclient import TestClient
from fsp_platform.db import session_scope
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]


@pytest.fixture
async def client(factory, db_url):
    data = load_taxonomy(CORE.parents[1] / "data" / "taxonomy")
    async with session_scope(factory) as s:
        await tax.sync(s, data)
    app = build_app(Settings(database_url=db_url, ui_bus_enabled=False))
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        c.redis = app.state.redis
        yield c


def _slugs(c, q="", **params):
    r = c.get("/taxonomy/skills/suggest", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return [i["slug"] for i in r.json()]


def test_prefix_of_synonym(client):
    # «пит» — начало синонима «питон»
    assert _slugs(client, "пит")[0] == "python"


def test_short_alias_exact_first(client):
    out = _slugs(client, "js")
    assert out[0] == "javascript"
    assert client.get("/taxonomy/skills/suggest", params={"q": "js"}).json()[0]["matched"] == "js"


def test_java_is_not_javascript(client):
    assert _slugs(client, "java")[0] == "java"
    out = _slugs(client, "javascript")
    assert (
        out[0] == "javascript" and "java" not in out
    )  # точно разные: через опечатки не подмешиваем
    typo = _slugs(client, "javascrpt")  # опечатка: триграммы находят JavaScript, но не Java
    assert typo and typo[0] == "javascript" and "java" not in typo


def test_fuzzy_typo_and_limit(client):
    assert _slugs(client, "pyton")[0] == "python"
    assert len(_slugs(client, "", limit=3)) == 3
    assert client.get("/taxonomy/skills/suggest", params={"limit": 0}).status_code == 422
    assert client.get("/taxonomy/skills/suggest", params={"limit": 51}).status_code == 422


async def test_frequency_and_provisional(client, factory):
    async with session_scope(factory) as s:
        sk = {
            x.slug: x
            for x in await s.scalars(select(Skill).where(Skill.slug.in_(("sql", "sqlite"))))
        }
        sk["sql"].support_candidates = 1
        sk["sqlite"].support_candidates = 500
        sk["sqlite"].status = "provisional"
    r = client.get("/taxonomy/skills/suggest", params={"q": "sql"})
    body = r.json()
    assert [i["slug"] for i in body][0] == "sql"  # точное совпадение выше частоты
    low = {i["slug"]: i for i in body}
    assert low["sqlite"]["provisional"] is True and low["sql"]["provisional"] is False


async def test_hidden_statuses_not_suggested(client, factory):
    async with session_scope(factory) as s:
        py = await s.scalar(select(Skill).where(Skill.slug == "python"))
        py.status = "rejected"
    assert "python" not in _slugs(client, "python")


def test_profession_boosts_own_skills(client):
    plain = _slugs(client, "")
    scoped = _slugs(client, "", profession="frontend", limit=50)
    assert "javascript" in scoped and "python" not in scoped
    assert plain != scoped


def test_kind_soft_only_soft_skills(client):
    # «Личные качества» — подсказки только из софт-навыков
    soft = _slugs(client, "", kind="soft", limit=50)
    assert "teamwork" in soft and "python" not in soft
    assert _slugs(client, "pyth", kind="soft") == []
    assert client.get("/taxonomy/skills/suggest", params={"kind": "x"}).status_code == 422


def test_public_and_cached(client):
    # без токена доступно (как /taxonomy)
    r = client.get("/taxonomy/professions/suggest", params={"q": "бэк"})
    assert r.status_code == 200
    first = _slugs(client, "py")
    keys = [k.decode() for k in client.portal.call(client.redis.keys, "c:tax:suggest:*")]
    assert any(k.startswith("c:tax:suggest:s:") for k in keys)
    assert _slugs(client, "py") == first


async def test_professions_include_admin_added_hidden_excluded(client, factory):
    r = client.get("/taxonomy/professions/suggest", params={"q": "back"})
    assert [i["slug"] for i in r.json()][:1] == ["backend"]
    async with session_scope(factory) as s:
        s.add(Role(slug="ghost", name="Призрак", is_profession=True, is_active=True))
        s.add(Role(slug="shadow", name="Тень", is_profession=True, is_active=False))

    assert [
        i["slug"] for i in client.get("/taxonomy/professions/suggest", params={"q": "призр"}).json()
    ] == ["ghost"]
    assert client.get("/taxonomy/professions/suggest", params={"q": "тен"}).json() == []
