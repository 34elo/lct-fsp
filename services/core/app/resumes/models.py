from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.candidates.models import TextArray
from app.identity.models import utcnow


class Resume(Base):
    """Загруженное резюме (data-model.md §3.2). `parsed` — ParsedResume из contracts."""

    __tablename__ = "resumes"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('queued','parsing','parsed','confirmed','failed')", name="ck_resumes_status"
        ),
        sa.Index("ix_resumes_candidate", "candidate_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    file_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="queued")
    parser_version: Mapped[str | None] = mapped_column(Text, default=None)
    parsed: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)


class Experience(Base):
    """Место работы (data-model.md §3.2); `skill_ids` — строки, как `top_evidence`."""

    __tablename__ = "experience"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    start_date: Mapped[date | None] = mapped_column(sa.Date, default=None)
    end_date: Mapped[date | None] = mapped_column(sa.Date, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    skill_ids: Mapped[list[str]] = mapped_column(TextArray, default=list)
    is_commercial: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    source: Mapped[str] = mapped_column(Text)  # resume | self


class Education(Base):
    __tablename__ = "education"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str | None] = mapped_column(Text, default=None)
    degree: Mapped[str | None] = mapped_column(Text, default=None)
    field: Mapped[str | None] = mapped_column(Text, default=None)
    year_end: Mapped[int | None] = mapped_column(default=None)
