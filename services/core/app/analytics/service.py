"""Запись продуктовых событий (metrics.md §2.4, §7).

`actor` — псевдоним `HMAC(id, ANALYTICS_SALT)`: соль только на сервере, по псевдониму
можно удалить сырые события пользователя, а восстановить id по событию нельзя.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from fsp_contracts.analytics import AnalyticsEvent, Source, validate_event
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import AnalyticsEventRow

log = structlog.get_logger()

_partitions: set[tuple[int, int]] = set()  # (год, месяц), для которых партиция уже создана


def pseudonym(salt: str, subject: uuid.UUID | str) -> str:
    digest = hmac.new(salt.encode(), str(subject).encode(), hashlib.sha256).hexdigest()
    return f"a_{digest[:32]}"


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    nxt = (year + (month == 12), month % 12 + 1)
    return datetime(year, month, 1, tzinfo=UTC), datetime(nxt[0], nxt[1], 1, tzinfo=UTC)


async def ensure_partition(session: AsyncSession, ts: datetime) -> None:
    """Партиция месяца события (только PostgreSQL; в SQLite таблица без партиций)."""
    if session.bind.dialect.name != "postgresql":
        return
    ts = ts.astimezone(UTC)
    key = (ts.year, ts.month)
    if key in _partitions:
        return
    lo, hi = _month_bounds(*key)
    name = f"analytics_events_{ts.year}_{ts.month:02d}"
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF analytics_events "
            f"FOR VALUES FROM ('{lo.isoformat()}') TO ('{hi.isoformat()}')"
        )
    )
    _partitions.add(key)


async def record(
    session: AsyncSession,
    events: Iterable[AnalyticsEvent],
    *,
    source: Source = "server",
) -> int:
    """Валидирует по схеме и пишет. Невалидное событие отбрасывается с логом (без props)."""
    rows = []
    for ev in events:
        try:
            ev = validate_event(ev, source)
        except ValueError as exc:  # UnknownAnalyticsEvent и pydantic.ValidationError
            log.warning("analytics_event_rejected", event=ev.event, error=type(exc).__name__)
            continue
        rows.append(ev.model_dump(mode="python"))
    for ts in {r["ts"] for r in rows}:
        await ensure_partition(session, ts)
    if rows:
        await session.execute(insert(AnalyticsEventRow), rows)
    return len(rows)


async def delete_by_actor(session: AsyncSession, actor: str) -> int:
    """Удаление профиля → удаление сырых событий по псевдониму (metrics.md §7)."""
    res = await session.execute(delete(AnalyticsEventRow).where(AnalyticsEventRow.actor == actor))
    return res.rowcount or 0
