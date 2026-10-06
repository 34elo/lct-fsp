"""Отправка событий аналитики блока 1 через `analytics.service` (blocks.md §4.7).

В props только числа, флаги, перечисления и slug'и. Ошибка аналитики не ломает основной поток.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import structlog
from fsp_contracts.analytics import AnalyticsEvent, Role
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.config import Settings

log = structlog.get_logger()


@lru_cache(maxsize=1)
def _salt() -> str:
    return Settings().analytics_salt


def slug(value: str) -> str:
    """Приводит идентификатор к `Slug` (латиница, цифры, `.+#_-`)."""
    return re.sub(r"[^a-z0-9.+#_-]", "_", value.lower())[:64] or "x"


async def emit(
    session: AsyncSession,
    name: str,
    candidate_id: uuid.UUID | None,
    props: dict[str, Any],
    *,
    role: Role = "candidate",
    now: datetime | None = None,
) -> None:
    """Пишет событие кандидата; невалидное отбрасывает `analytics.record` с логом."""
    try:
        ev = AnalyticsEvent(
            event=name,
            ts=now or datetime.now(UTC),
            actor=analytics.pseudonym(_salt(), candidate_id) if candidate_id else None,
            role=role,
            channel="system",
            props={k: v for k, v in props.items() if v is not None},
        )
        async with session.begin_nested():
            await analytics.record(session, [ev])
    except Exception as exc:  # аналитика не должна ронять тест
        log.warning("assessment_analytics_failed", analytics_event=name, error=type(exc).__name__)
