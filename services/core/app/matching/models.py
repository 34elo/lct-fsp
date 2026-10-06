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
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=sa.func.now()
    )
