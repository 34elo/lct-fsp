"""Outbox и inbox (messaging.md §2.3).

Событие пишется в outbox в той же транзакции, что и данные. Relay публикует его
и только после подтверждения ставит published_at. Обработчик идемпотентен: inbox.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fsp_contracts import Envelope
from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fsp_platform.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")
_ID = BigInteger().with_variant(Integer(), "sqlite")


class OutboxRecord(Base):
    __tablename__ = "outbox"

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
