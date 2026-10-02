"""Распределённые блокировки на Redis (`lock:*`, messaging.md §5)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end
"""


class LockNotAcquired(Exception):
    pass


async def acquire(redis: Redis, name: str, ttl: int) -> str | None:
    """Токен владельца или None, если замок занят. TTL — секунды."""
    token = uuid.uuid4().hex
    ok = await redis.set(f"lock:{name}", token, nx=True, ex=ttl)
    return token if ok else None


async def release(redis: Redis, name: str, token: str) -> bool:
    """Снимает замок только владельцем (по токену)."""
    return bool(await redis.eval(_RELEASE, 1, f"lock:{name}", token))


@asynccontextmanager
async def redis_lock(redis: Redis, name: str, ttl: int = 60) -> AsyncIterator[str]:
    token = await acquire(redis, name, ttl)
    if token is None:
        raise LockNotAcquired(name)
    try:
        yield token
    finally:
        await release(redis, name, token)
