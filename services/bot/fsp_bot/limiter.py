"""Token bucket для исходящих сообщений: глобально 25/с и 1/с на чат."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(rate, 1.0)
        self._clock, self._sleep = clock, sleep
        self._tokens = self.capacity
        self._stamp = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._stamp) * self.rate)
        self._stamp = now

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens < 1:
                await self._sleep((1 - self._tokens) / self.rate)
                self._refill()
            self._tokens -= 1


class SendLimiter:
    """Сначала слот чата (чтобы не занимать глобальный токен ожиданием), затем глобальный."""

    def __init__(
        self,
        global_rate: float = 25.0,
        per_chat_rate: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_chats: int = 10_000,
    ):
        self._clock, self._sleep = clock, sleep
        self._global = TokenBucket(global_rate, clock=clock, sleep=sleep)
        self._per_chat = per_chat_rate
        self._chats: dict[int, TokenBucket] = {}
        self._max_chats = max_chats

    def _chat_bucket(self, chat_id: int) -> TokenBucket:
        bucket = self._chats.get(chat_id)
        if bucket is None:
            if len(self._chats) >= self._max_chats:
                # Полные корзины эквивалентны отсутствующим: их можно выбросить
                full = [c for c, b in self._chats.items() if b._tokens >= b.capacity]
                for c in full or list(self._chats)[: self._max_chats // 2]:
                    del self._chats[c]
            bucket = self._chats[chat_id] = TokenBucket(
                self._per_chat, 1.0, clock=self._clock, sleep=self._sleep
            )
        return bucket

    async def acquire(self, chat_id: int) -> None:
        await self._chat_bucket(chat_id).acquire()
        await self._global.acquire()
