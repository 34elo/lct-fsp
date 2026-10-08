"""Alembic (async). URL: -x url=... , иначе DATABASE_URL из окружения/.env."""

from __future__ import annotations

import asyncio

from alembic import context
from fsp_connector.config import Settings
from fsp_connector.models import metadata
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config


def _url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or Settings().database_url


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_async())
