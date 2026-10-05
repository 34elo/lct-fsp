"""Общие фикстуры core (blocks.md §5.8): БД из миграций, сессия, HTTP-клиент.

Миграции гоняются один раз на сессию pytest, дальше копируется файл SQLite.
Тест эндпоинта в 10 строк — см. `tests/test_scaffold.py`.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
# import-mode=importlib: тесты видят factories и core_helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory) -> Path:
    """Файл SQLite с миграциями `head`: шаблон, который копируют тесты."""
    db = tmp_path_factory.mktemp("core-template") / "template.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return db


@pytest.fixture
def db_path(tmp_path, migrated_db) -> Path:
    path = tmp_path / "core.db"
    shutil.copy(migrated_db, path)
    return path


@pytest.fixture
def db_url(db_path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture
async def factory(db_url):
    engine = make_engine(db_url)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def session(factory):
    """Сессия с коммитом на выходе: фабрики из `tests/factories` делают flush."""
    async with session_scope(factory) as s:
        yield s


@pytest.fixture
def api(db_path):
    """TestClient поверх `build_app` с чистой БД и fakeredis."""
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db_path}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db_path = db_path
        yield client
