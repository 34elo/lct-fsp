"""Таблицы базы `fsp_connector` (data-model.md §3.10). outbox/inbox — из платформы."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_
from uuid import UUID

from fsp_platform.db import Base
from fsp_platform.outbox import InboxRecord, OutboxRecord  # noqa: F401
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
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
    method: Mapped[str] = mapped_column(String)  # oauth | code | manual | registry
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    sync_cursor: Mapped[str | None] = mapped_column(String, default=None)


class FspLinkConflict(Base):
    """Попытка привязать уже занятый participant_id: запись для модерации (fsp.md §4)."""

    __tablename__ = "fsp_link_conflicts"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    candidate_id: Mapped[UUID] = mapped_column()  # кто пытался привязать
    participant_id: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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


# ------------------------------------------------------------------ реестр ФСП (E39-28, ADR-052)
class RegistryEvent(Base):
    """Мероприятие реестра: заводит админ. Для core это обычное соревнование ФСП."""

    __tablename__ = "fsp_reg_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "e-<hex>"
    title: Mapped[str] = mapped_column(String)
    discipline: Mapped[str] = mapped_column(String)  # FspDiscipline
    level: Mapped[str] = mapped_column(String)  # FspLevel
    date: Mapped[date_] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RegistryParticipant(Base):
    """Участник реестра. ПДн (ФИО, email, телефон) живут только здесь.

    Поиск — по нормализованным `email_norm` / `phone_norm`.
    """

    __tablename__ = "fsp_reg_participants"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "r-<hex>" или ID в источнике ФСП
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, default=None)
    phone: Mapped[str | None] = mapped_column(String, default=None)
    email_norm: Mapped[str | None] = mapped_column(String, default=None, index=True)
    phone_norm: Mapped[str | None] = mapped_column(String, default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RegistryResult(Base):
    """Результат: участник × мероприятие (место, команда)."""

    __tablename__ = "fsp_reg_results"
    __table_args__ = (UniqueConstraint("participant_id", "event_id"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("fsp_reg_participants.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("fsp_reg_events.id", ondelete="CASCADE"), index=True
    )
    place: Mapped[int | None] = mapped_column(Integer, default=None)
    team: Mapped[str | None] = mapped_column(String, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LinkRequest(Base):
    """Заявка кандидата на привязку, когда его email/телефон не нашёлся в реестре."""

    __tablename__ = "fsp_link_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    candidate_id: Mapped[UUID] = mapped_column(index=True)  # без FK: другая база
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, default=None)
    phone: Mapped[str | None] = mapped_column(String, default=None)
    event: Mapped[str | None] = mapped_column(String, default=None)  # название мероприятия
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|accepted|rejected
    reason: Mapped[str | None] = mapped_column(String, default=None)
    participant_id: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


metadata = Base.metadata
