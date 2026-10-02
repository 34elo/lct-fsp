"""Ретраи с экспоненциальной паузой и circuit breaker (fsp.md §2)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog

from fsp_connector.errors import FspUnavailable

log = structlog.get_logger()


class Transient(Exception):
    """Временный сбой источника (сеть, 5xx, 429): стоит повторить."""


class CircuitBreaker:
    """После `failures` подряд сбоев размыкается на `open_seconds`, затем пускает пробный запрос."""

    def __init__(
        self,
        failures: int = 5,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failures = failures
        self.open_seconds = open_seconds
        self._clock = clock
        self._count = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None and self._clock() - self._opened_at < self.open_seconds

    def record_success(self) -> None:
        self._count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._count += 1
        if self._count >= self.failures:
            self._opened_at = self._clock()


async def call_with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    breaker: CircuitBreaker,
    retries: int = 3,
    base_delay: float = 0.2,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """`fn` бросает `Transient` для повторяемых сбоев; остальные исключения не ретраятся."""
    if breaker.is_open:
        raise FspUnavailable("circuit breaker открыт")
    attempts = max(1, retries)
    for attempt in range(attempts):
        try:
            result = await fn()
        except Transient as exc:
            breaker.record_failure()
            log.warning("fsp_transient_error", attempt=attempt + 1, error=str(exc))
            if attempt + 1 >= attempts or breaker.is_open:
                raise FspUnavailable("источник ФСП недоступен") from exc
            await sleep(base_delay * 2**attempt)
        else:
            breaker.record_success()
            return result
    raise FspUnavailable("источник ФСП недоступен")  # недостижимо, для типизации
