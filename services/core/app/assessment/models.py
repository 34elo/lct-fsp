"""Таблица `grades` (blocks.md §4.2): текущий подтверждённый грейд кандидата по профессии.

Пишет только блок 1 (E22-4 и `seed_grade`), блок 2 читает через `service.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class Grade(Base):
    __tablename__ = "grades"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    profession: Mapped[str] = mapped_column(Text, primary_key=True)  # ProfessionSlug
    grade: Mapped[str] = mapped_column(Text)  # TestGrade
    theta: Mapped[float] = mapped_column(sa.Float)
    se: Mapped[float | None] = mapped_column(sa.Float, default=None)
    band_position: Mapped[float] = mapped_column(sa.Float)  # T ∈ [0, 1]
    theta_by_type: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    integrity: Mapped[float] = mapped_column(sa.Float, default=1.0, server_default="1.0")
    needs_confirmation: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    low_confidence: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    source: Mapped[str] = mapped_column(Text)  # test | seed
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(default=None)  # FK добавит Б1 с attempts
    confirmed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    next_change_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (sa.Index("ix_grades_profession_grade", "profession", "grade"),)
