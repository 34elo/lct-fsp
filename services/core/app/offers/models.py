from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


class Offer(Base):
    """Оффер (data-model.md §3.8). Вилка обязательна; статусы — `OfferStatus`.

    ADR-022: `vacancy_id` пуст у приглашения без вакансии (тогда обязателен `title`);
    `initiator` — `employer` (приглашение) или `candidate` (отклик).
    """

    __tablename__ = "offers"
    __table_args__ = (
        sa.UniqueConstraint("vacancy_id", "candidate_id", name="uq_offers_vacancy_candidate"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_offers_company_idem"),
        sa.CheckConstraint("salary_to >= salary_from", name="ck_offers_salary_range"),
        sa.Index("ix_offers_candidate_created", "candidate_id", sa.text("created_at DESC")),
        sa.Index("ix_offers_company_created", "company_id", sa.text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vacancies.id"), default=None)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="SET NULL"), default=None
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    salary_from: Mapped[int]
    salary_to: Mapped[int]
    salary_basis: Mapped[str] = mapped_column(Text, default="gross", server_default="gross")
    message: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    contact_method: Mapped[str | None] = mapped_column(Text, default=None)
    initiator: Mapped[str] = mapped_column(Text, default="employer", server_default="employer")
    status: Mapped[str] = mapped_column(Text, default="sent", server_default="sent")
    decline_reason: Mapped[str | None] = mapped_column(Text, default=None)
    decline_comment: Mapped[str | None] = mapped_column(Text, default=None)
    awaiting_reply_from: Mapped[str | None] = mapped_column(Text, default=None)
    match_snapshot: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    below_candidate_min: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    team_offer_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    idempotency_key: Mapped[str | None] = mapped_column(Text, default=None)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    responded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class OfferEvent(Base):
    """Журнал переходов оффера (кто, откуда, куда)."""

    __tablename__ = "offer_events"

    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(Text, default=None)
    to_status: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)  # candidate | company | system
    payload: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class OfferMessage(Base):
    """Сообщение в переписке по офферу (`author_side`: candidate | company)."""

    __tablename__ = "offer_messages"
    __table_args__ = (sa.Index("ix_offer_messages_offer_created", "offer_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    author_side: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    channel: Mapped[str | None] = mapped_column(Text, default=None)  # web | telegram


class ContactReveal(Base):
    """Факт раскрытия контактов; одна строка на оффер, создаётся при `accepted`."""

    __tablename__ = "contact_reveals"

    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id"), primary_key=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    company_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    revealed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    # E32-5a: кандидат отозвал доступ к контактам; после отзыва компания их не видит
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)


class Complaint(Base):
    """Жалоба кандидата на оффер/компанию; разбирает админ (E12)."""

    __tablename__ = "complaints"
    __table_args__ = (
        sa.UniqueConstraint("offer_id", "reporter_user_id", name="uq_complaints_offer_reporter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id"))
    reporter_user_id: Mapped[uuid.UUID] = mapped_column()
    reason: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
