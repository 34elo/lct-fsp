"""Outbox и inbox.

Событие пишется в outbox в той же транзакции, что и данные. Relay публикует его
и только после подтверждения ставит published_at. Обработчик идемпотентен: inbox.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import asyncpg
import structlog
from fsp_contracts import Envelope
from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from fsp_platform.db import Base

log = structlog.get_logger()
NOTIFY_CHANNEL = "outbox"

# PostgreSQL: NOTIFY после commit транзакции со вставкой в outbox — relay просыпается сразу.
OUTBOX_NOTIFY_DDL = (
    """
    CREATE OR REPLACE FUNCTION outbox_notify() RETURNS trigger AS $$
    BEGIN
        PERFORM pg_notify('outbox', '');
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS outbox_notify ON outbox",
    """
    CREATE TRIGGER outbox_notify AFTER INSERT ON outbox
    FOR EACH STATEMENT EXECUTE FUNCTION outbox_notify()
    """,
)
OUTBOX_NOTIFY_DROP = (
    "DROP TRIGGER IF EXISTS outbox_notify ON outbox",
    "DROP FUNCTION IF EXISTS outbox_notify()",
)

_JSON = JSON().with_variant(JSONB(), "postgresql")
_ID = BigInteger().with_variant(Integer(), "sqlite")


class OutboxRecord(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "ix_outbox_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
            sqlite_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    type: Mapped[str] = mapped_column(String)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    payload: Mapped[dict] = mapped_column(_JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class InboxRecord(Base):
    __tablename__ = "inbox"

    message_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    handler: Mapped[str] = mapped_column(String, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


async def add_to_outbox(
    session: AsyncSession, envelope: Envelope, aggregate_id: uuid.UUID | None = None
) -> OutboxRecord:
    """Вызывать в транзакции бизнес-данных: commit делает вызывающий."""
    rec = OutboxRecord(
        event_id=envelope.message_id,
        type=envelope.type,
        aggregate_id=aggregate_id,
        payload=envelope.model_dump(mode="json"),
    )
    session.add(rec)
    await session.flush()
    return rec


async def relay_once(
    session: AsyncSession,
    publish: Callable[[Envelope], Awaitable[None]],
    batch: int = 100,
) -> int:
    """Публикует неотправленные события по порядку. published_at только после успеха publish."""
    stmt = (
        select(OutboxRecord)
        .where(OutboxRecord.published_at.is_(None))
        .order_by(OutboxRecord.id)
        .limit(batch)
        .with_for_update(skip_locked=True)
    )
    sent = 0
    for rec in (await session.execute(stmt)).scalars():
        await publish(Envelope.model_validate(rec.payload))
        await session.execute(
            update(OutboxRecord)
            .where(OutboxRecord.id == rec.id)
            .values(published_at=datetime.now(UTC))
        )
        sent += 1
    await session.commit()
    return sent


async def claim_inbox(session: AsyncSession, message_id: uuid.UUID, handler: str) -> bool:
    """True — сообщение обрабатываем впервые; False — повторная доставка, пропускаем."""
    try:
        async with session.begin_nested():
            session.add(InboxRecord(message_id=message_id, handler=handler))
            await session.flush()
    except IntegrityError:
        return False
    return True


class OutboxRelay:
    """Фоновый relay: LISTEN outbox (мгновенно) + опрос раз в `poll_interval` (страховка).

    Несколько экземпляров безопасны: строки берутся `FOR UPDATE SKIP LOCKED`.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publish: Callable[[Envelope], Awaitable[None]],
        *,
        listen_dsn: str | None = None,
        poll_interval: float = 0.5,
        batch: int = 100,
    ):
        self.session_factory = session_factory
        self.publish = publish
        self.listen_dsn = listen_dsn
        self.poll_interval = poll_interval
        self.batch = batch
        self._wake = asyncio.Event()

    async def _listen(self) -> asyncpg.Connection | None:
        if not self.listen_dsn or not self.listen_dsn.startswith("postgresql"):
            return None
        dsn = self.listen_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        try:
            conn = await asyncpg.connect(dsn)
            await conn.add_listener(NOTIFY_CHANNEL, lambda *_: self._wake.set())
        except Exception as exc:
            log.warning("outbox_listen_unavailable", error=type(exc).__name__)
            return None
        return conn

    async def run(self) -> None:
        conn = await self._listen()
        try:
            while True:
                self._wake.clear()
                try:
                    async with self.session_factory() as session:
                        sent = await relay_once(session, self.publish, self.batch)
                except Exception as exc:
                    log.warning("outbox_relay_failed", error=type(exc).__name__)
                    sent = 0
                if sent >= self.batch:
                    continue
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), self.poll_interval)
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close()
