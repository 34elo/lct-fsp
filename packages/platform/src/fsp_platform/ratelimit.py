"""Лимитер со скользящим окном на Redis (messaging.md §7). Ключи `rl:*`."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis

from fsp_platform.app import ProblemError


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    remaining: int
    retry_after: int  # секунды до освобождения слота (0, если разрешено)


class RateLimiter:
    def __init__(self, redis: Redis, prefix: str = "rl"):
        self._redis, self._prefix = redis, prefix

    async def hit(self, key: str, limit: int, window: int) -> RateResult:
        """Учесть обращение. Отклонённые попытки в окно не засчитываются."""
        rkey = f"{self._prefix}:{key}"
        now = time.time()
        pipe = self._redis.pipeline(transaction=True)
        pipe.zremrangebyscore(rkey, 0, now - window)
        pipe.zcard(rkey)
        pipe.zrange(rkey, 0, 0, withscores=True)
        _, count, oldest = await pipe.execute()
        if count >= limit:
            retry = max(1, int(oldest[0][1] + window - now) + 1) if oldest else window
            return RateResult(False, 0, retry)
        pipe = self._redis.pipeline(transaction=True)
        pipe.zadd(rkey, {uuid.uuid4().hex: now})
        pipe.expire(rkey, window)
        await pipe.execute()
        return RateResult(True, limit - count - 1, 0)

    async def check(self, key: str, limit: int, window: int, code: str = "rate_limited") -> None:
        """Бросает 429 Problem Details с Retry-After."""
        res = await self.hit(key, limit, window)
        if not res.allowed:
            raise ProblemError(
                429,
                code,
                "Слишком много запросов",
                headers={"Retry-After": str(res.retry_after)},
            )
