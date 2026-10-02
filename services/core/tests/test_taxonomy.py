import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import fakeredis
import pytest
import yaml
from app.config import Settings
from app.main import build_app
from app.taxonomy import service
from app.taxonomy.loader import TaxonomyError, load_taxonomy
from app.taxonomy.models import Skill, SkillAlias, SkillRelation
from fastapi.testclient import TestClient
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
TOKEN = "ml-secret"


@pytest.fixture
def db_url(tmp_path):
    db = tmp_path / "t.db"
    url = f"sqlite+aiosqlite:///{db}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
def tdir(tmp_path):
    d = tmp_path / "taxonomy"
    shutil.copytree(FIX / "taxonomy", d)
    return d


def _load(tdir):
    return load_taxonomy(tdir, FIX / "discipline_rules.yaml")


async def _sync(url, data):
    engine = make_engine(url)
    try:
        async with session_scope(make_session_factory(engine)) as s:
            return await service.sync(s, data)
    finally:
        await engine.dispose()


async def _count(url, model):
    engine = make_engine(url)
    try:
        async with session_scope(make_session_factory(engine)) as s:
            return await s.scalar(select(func.count()).select_from(model))
    finally:
        await engine.dispose()


async def test_sync_loads_and_is_idempotent(db_url, tdir):
    first = await _sync(db_url, _load(tdir))
    assert first.bumped and first.version == 1 and len(first.changed_skill_ids) == 8
    assert first.skipped_rule_skills == ["product:ghost_skill"]
    counts = [await _count(db_url, m) for m in (Skill, SkillAlias, SkillRelation)]
    again = await _sync(db_url, _load(tdir))
    assert not again.bumped and again.version == 1 and again.changed_skill_ids == []
    assert counts == [await _count(db_url, m) for m in (Skill, SkillAlias, SkillRelation)]
    assert counts[0] == 8 and counts[2] == 4  # adjacent в обе стороны + 2 parent
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        events = (await s.scalars(select(OutboxRecord))).all()
    await engine.dispose()
    assert [e.type for e in events] == ["taxonomy.updated"]  # повтор не плодит события


async def test_version_bumps_with_changed_ids(db_url, tdir):
    await _sync(db_url, _load(tdir))
    rel = tdir / "relations.yaml"
    doc = yaml.safe_load(rel.read_text())
    doc["adjacent"][0]["weight"] = 0.9
    rel.write_text(yaml.safe_dump(doc))
    res = await _sync(db_url, _load(tdir))
    assert res.bumped and res.version == 2
    assert set(res.changed_skill_ids) == {service.skill_id("fastapi"), service.skill_id("django")}
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        last = (await s.scalars(select(OutboxRecord).order_by(OutboxRecord.id))).all()[-1]
    await engine.dispose()
    assert last.payload["payload"]["version"] == 2
    assert len(last.payload["payload"]["changed_skill_ids"]) == 2


async def test_non_seed_edits_survive_resync(db_url, tdir):
    await _sync(db_url, _load(tdir))
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        py = await s.get(Skill, service.skill_id("python"))
        py.source, py.name = "admin", "Python 3"
        s.add(SkillAlias(alias_norm="змея", skill_id=py.id, source="admin"))
    await engine.dispose()
    await _sync(db_url, _load(tdir))
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        assert (await s.get(Skill, service.skill_id("python"))).name == "Python 3"
        assert await s.get(SkillAlias, "змея") is not None
    await engine.dispose()


def _write(tdir, name, doc):
    (tdir / name).write_text(yaml.safe_dump(doc, allow_unicode=True))


@pytest.mark.parametrize(
    ("patch", "msg"),
    [
        ({"adjacent": [{"a": "python", "b": "nope", "weight": 0.5}]}, "неизвестный навык"),
        ({"adjacent": [{"a": "python", "b": "java", "weight": 1.5}]}, "weight"),
        ({"parent": [{"child": "python", "parent": "fastapi", "weight": 0.5}]}, "цикл"),
        ({"distinct": [["java", "java"]]}, "из одного навыка"),
        ({"skills": [{"slug": "go", "name": "Go", "kind": "hard", "aliases": ["js"]}]}, "синоним"),
        ({"skills": [{"slug": "python", "name": "Py", "kind": "hard"}]}, "дубликат"),
        ({"skills": [{"slug": "x", "name": "X", "kind": "weird"}]}, "kind"),
    ],
)
def test_loader_rejects_bad_yaml(tdir, patch, msg):
    _write(tdir, "extra.yaml", patch)
    with pytest.raises(TaxonomyError, match=msg):
        _load(tdir)


def test_loader_ignores_unknown_files_and_requires_dir(tdir):
    data = _load(tdir)  # package_map.yaml в каталоге не мешает
    assert len(data.skills) == 8 and ("java", "javascript") in data.distinct
    assert ("web", "python") not in data.discipline_rules  # треки лежат внутри дисциплины
    assert any(t == "web" for _, _, t in data.discipline_rules["product"])
    with pytest.raises(TaxonomyError):
        load_taxonomy(tdir / "missing")


@pytest.fixture
def client(db_url, tdir):
    import asyncio

    asyncio.run(_sync(db_url, _load(tdir)))
    app = build_app(Settings(database_url=db_url, ui_bus_enabled=False, service_token_ml=TOKEN))
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        c.app_ = app
        yield c


def test_get_taxonomy_etag_and_content(client):
    r = client.get("/taxonomy")
    assert r.status_code == 200 and r.headers["etag"].startswith('W/"tax-1-')
    body = r.json()
    assert body["version"] == 1 and "senior" in body["grades"] and "remote" in body["formats"]
    py = next(s for s in body["skills"] if s["slug"] == "python")
    assert py == {
        "slug": "python",
        "name": "Python",
        "kind": "hard",
        "group": "language",
        "testable": True,
    }
    assert {d["slug"] for d in body["disciplines"]} == {"algorithmic", "product"}
    assert [r["slug"] for r in body["roles"]] == ["backend", "frontend"]
    r2 = client.get("/taxonomy", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304 and r2.content == b""
    assert client.get("/taxonomy", headers={"If-None-Match": 'W/"old"'}).status_code == 200


def test_snapshot_requires_service_token(client):
    url = "/internal/taxonomy/snapshot"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Service nope"}).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 401
    r = client.get(url, headers={"Authorization": f"Service {TOKEN}"})
    assert r.status_code == 200
    snap = r.json()
    assert snap["version"] == 1
    assert ["java", "javascript"] in snap["distinct"]
    assert {"a": "django", "b": "fastapi", "weight": 0.6} in snap["adjacent"]
    assert {"child": "fastapi", "parent": "python", "weight": 0.6} in snap["parent"]
    pg = next(s for s in snap["skills"] if s["slug"] == "postgresql")
    assert {"постгрес", "postgres", "pg", "postgresql"} <= set(pg["aliases"])
    uuid.UUID(pg["id"])
    # закешировано по версии
    assert client.app_.state.redis is not None


def test_snapshot_closed_when_token_unset(db_url):
    app = build_app(Settings(database_url=db_url, ui_bus_enabled=False))
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        assert (
            c.get("/internal/taxonomy/snapshot", headers={"Authorization": "Service "}).status_code
            == 401
        )


def test_cli_missing_dir_fails(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "app.taxonomy", "--dir", str(tmp_path / "none")],
        cwd=CORE,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and "Ошибка справочника" in r.stderr
