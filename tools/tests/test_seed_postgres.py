"""E42-3: сид на чистом Postgres проходит с первого раза и повторяется без ошибок.

Нужен пустой Postgres с pgvector: `SEED_PG_URL=postgresql+asyncpg://user:pw@host:port/db`
(например, docker run с образом pgvector/pgvector:pg16, POSTGRES_DB=core, порт 29432).
Без переменной тест пропускается.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("SEED_PG_URL")

pytestmark = pytest.mark.skipif(not URL, reason="нужен SEED_PG_URL (пустой Postgres с pgvector)")


def _run(args: list[str], cwd: Path) -> None:
    env = {**os.environ, "DATABASE_URL": URL or "", "SEED": "20261003"}
    r = subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=900
    )
    assert r.returncode == 0, f"{args}: {(r.stdout + r.stderr)[-1500:]}"


def test_seed_chain_on_clean_postgres_twice():
    core = ROOT / "services" / "core"
    _run(["-m", "alembic", "upgrade", "head"], core)
    _run(["-m", "app.taxonomy"], core)
    (ROOT / "reports" / "seed").mkdir(parents=True, exist_ok=True)
    for _ in range(2):  # второй проход — идемпотентность (prod-init повторяем)
        for step in ("all", "grades", "families", "demo2"):
            _run(["-m", "tools.seed", step], ROOT)


def test_expire_due_on_seed_data_postgres():
    """E42-4: на данных сида просроченные приглашения истекают без ошибки, повтор — no-op."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    core = str(ROOT / "services" / "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    from app.offers import service

    async def run() -> tuple[int, int, int]:
        engine = create_async_engine(URL)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as s:  # все ждущие ответа (и интересы) делаем просроченными
                await s.execute(
                    text(
                        "update offers set expires_at = now() - interval '1 hour' "
                        "where status in ('sent','viewed')"
                    )
                )
                await s.execute(
                    text(
                        "update offers set status='interest', interest_at=now(), "
                        "invited_at=null, expires_at=now() - interval '1 hour' where id in "
                        "(select id from offers where status='declined' limit 3)"
                    )
                )
                total = 0
                while n := await service.expire_due(s):
                    total += n
                again = await service.expire_due(s)
                left = await s.scalar(
                    text(
                        "select count(*) from offers where expires_at <= now() and "
                        "status in ('sent','viewed','interest','interest_opened')"
                    )
                )
                await s.rollback()
                return total, again, left
        finally:
            await engine.dispose()

    total, again, left = asyncio.run(run())
    assert total > 0 and again == 0 and left == 0
