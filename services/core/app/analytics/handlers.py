"""Очередь `core.analytics`: доменные события → `analytics_events` (E18-1).

Подписка только на отображаемые типы; остальное очередь молча пропускает.
`candidate.deleted` удаляет сырые события пользователя по псевдониму (metrics.md §7).
"""

from __future__ import annotations

from collections.abc import Mapping

from fsp_contracts import Envelope
from fsp_contracts.events import CandidateDeleted
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics import service
from app.analytics.mapper import MAPPERS, map_event


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    salt: str,
) -> None:
    @consumers["core.analytics"].on(*MAPPERS)
    @idempotent(session_factory, "analytics.record")
    async def on_event(envelope: Envelope, session: AsyncSession) -> None:
        await service.record(session, map_event(envelope, salt))

    @consumers["core.analytics"].on("candidate.deleted")
    @idempotent(session_factory, "analytics.forget")
    async def on_deleted(envelope: Envelope, session: AsyncSession) -> None:
        ev = CandidateDeleted.model_validate(envelope.payload)
        await service.delete_by_actor(session, service.pseudonym(salt, ev.candidate_id))
