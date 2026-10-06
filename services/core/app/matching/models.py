from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


class Match(Base):
    """Подборка «вакансия — кандидат» (data-model.md §3.7); пишет только модуль matching."""

    __tablename__ = "matches"
    __table_args__ = (sa.Index("ix_matches_vacancy_score", "vacancy_id", sa.text("score DESC")),)

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(sa.Float)
    breakdown: Mapped[dict] = mapped_column(sa.JSON)
    explanation: Mapped[list] = mapped_column(sa.JSON)
    rationale: Mapped[str | None] = mapped_column(Text, default=None)  # LLM для топ-5 (E7-9)
    candidate_version: Mapped[int]
    vacancy_version: Mapped[int]
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class Need(Base):
    """Потребность работодателя (assessment.md §9, E23-4): текст, фильтры и веса навыков."""

    __tablename__ = "needs"
    __table_args__ = (sa.Index("ix_needs_company", "company_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    text: Mapped[str | None] = mapped_column(Text, default=None)
    filters: Mapped[dict] = mapped_column(sa.JSON)  # SearchFilters
    weights: Mapped[dict] = mapped_column(sa.JSON)  # slug навыка → вес потребности
    grades: Mapped[list] = mapped_column(sa.JSON)  # грейды теста из потребности
    # pseudo_id кандидатов в шорт-листе (E23-5)
    shortlist: Mapped[list[str]] = mapped_column(sa.JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=sa.func.now()
    )


class CategorySubscription(Base):
    """Подписка компании на категорию (E33-4): новый подходящий кандидат → уведомление."""

    __tablename__ = "category_subscriptions"
    __table_args__ = (sa.Index("ix_category_subs_profession", "profession"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    profession: Mapped[str] = mapped_column(Text)
    grades: Mapped[list] = mapped_column(sa.JSON, default=list)  # пусто — любой грейд
    skills: Mapped[list] = mapped_column(sa.JSON, default=list)  # [{slug, min_level}]
    salary_max: Mapped[int | None] = mapped_column(default=None)  # бюджет, ₽/мес
    formats: Mapped[list] = mapped_column(sa.JSON, default=list)
    only_confirmed: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    last_digest_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=sa.func.now()
    )


class CategorySubscriptionHit(Base):
    """Подошедший подписке кандидат. PK — дедупликация: один кандидат уведомляет один раз."""

    __tablename__ = "category_subscription_hits"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("category_subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=sa.func.now()
    )
    notified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
