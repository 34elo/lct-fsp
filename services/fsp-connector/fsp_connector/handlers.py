"""Обработчики очереди `fsp.sync`: `fsp.sync` и `fsp.sync_all`."""

from __future__ import annotations

from collections.abc import Mapping

from fsp_contracts import Envelope
from fsp_contracts.commands import FspSync
from fsp_platform.locks import redis_lock
from fsp_platform.messaging import Consumer, idempotent
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fsp_connector.sync import SyncService

LOCK_TTL = 120


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    sync: SyncService,
    redis: Redis,
) -> None:
    @consumers["fsp.sync"].on("fsp.sync")
    @idempotent(session_factory, "fsp.sync")
    async def on_sync(envelope: Envelope, session: AsyncSession) -> None:
        cmd = FspSync.model_validate(envelope.payload)
        # занятый замок -> LockNotAcquired -> ретрай очереди (параллельная синхронизация уже идёт)
        async with redis_lock(redis, f"fsp_sync:{cmd.candidate_id}", LOCK_TTL):
            await sync.sync_candidate(session, cmd.candidate_id, reason=cmd.reason, since=cmd.since)

    @consumers["fsp.sync"].on("fsp.sync_all")
    @idempotent(session_factory, "fsp.sync_all")
    async def on_sync_all(envelope: Envelope, session: AsyncSession) -> None:
        await sync.sync_all()
