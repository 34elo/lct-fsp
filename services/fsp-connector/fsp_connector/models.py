"""Таблицы базы `fsp_connector` (data-model.md §3.10). outbox/inbox — из платформы."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fsp_platform.db import Base
from fsp_platform.outbox import InboxRecord, OutboxRecord  # noqa: F401
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

_JSON = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(UTC)


class FspLink(Base):
    """Привязка кандидата core к участнику ФСП. Один participant_id — один кандидат."""

    __tablename__ = "fsp_links"

    candidate_id: Mapped[UUID] = mapped_column(primary_key=True)  # без FK: другая база
    participant_id: Mapped[str] = mapped_column(String, unique=True)
    verified: Mapped[bool] = mapped_column(Boolean)
    method: Mapped[str] = mapped_column(String)  # oauth | code | manual
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    sync_cursor: Mapped[str | None] = mapped_column(String, default=None)


class RawResponse(Base):
    """Аудит: сырые ответы источника."""

    __tablename__ = "raw_responses"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    participant_id: Mapped[str | None] = mapped_column(String, default=None)
    endpoint: Mapped[str] = mapped_column(String)
    body: Mapped[dict | list] = mapped_column(_JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WebhookLog(Base):
    """Журнал вебхуков; `event_id` — ключ идемпотентности."""

    __tablename__ = "webhook_log"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(_JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


metadata = Base.metadata
