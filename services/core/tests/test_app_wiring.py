from typing import Annotated

import fakeredis
from app.config import Settings
from app.deps import get_session
from app.main import build_app
from fastapi import Depends
from fastapi.testclient import TestClient
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _client(tmp_path):
    s = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db")
    return build_app(s)


def test_lifespan_session_dependency_and_readyz(tmp_path):
    app = _client(tmp_path)

    @app.get("/count")
    async def count(session: Annotated[AsyncSession, Depends(get_session)]):
        return len((await session.execute(select(OutboxRecord))).scalars().all())

    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        assert c.get("/readyz").json() == {"status": "ready"}
        assert c.get("/healthz").json() == {"status": "ok"}


def test_readyz_503_problem_when_redis_down(tmp_path):
    app = build_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", redis_url="redis://127.0.0.1:1/0"
        )
    )
    with TestClient(app) as c:
        r = c.get("/readyz")
        assert r.status_code == 503 and r.json()["code"] == "not_ready"
