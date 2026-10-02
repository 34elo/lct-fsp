"""Зависимости FastAPI: сессия БД, Redis, лимитер, хранилище."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from fsp_platform.db import session_scope
from fsp_platform.ratelimit import RateLimiter
from fsp_platform.storage import ObjectStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Одна транзакция на запрос: commit при успехе, rollback при ошибке."""
    async with session_scope(request.app.state.session_factory) as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage
