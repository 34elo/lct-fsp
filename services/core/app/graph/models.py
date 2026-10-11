from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.candidates.models import TextArray
from app.identity.models import utcnow


class Evidence(Base):
    """Ребро «факт подтверждает навык»; ключ upsert — uq_evidence_fact."""

    __tablename__ = "evidence"
    __table_args__ = (
        sa.UniqueConstraint(
            "candidate_id", "skill_id", "source", "fact_type", "fact_id", name="uq_evidence_fact"
        ),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name="ck_evidence_strength"),
        sa.Index("ix_evidence_skill_id", "skill_id"),
        sa.Index("ix_evidence_fact", "fact_type", "fact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"))
    source: Mapped[str] = mapped_column(Text)
    strength: Mapped[float] = mapped_column(sa.Float)
    observed_at: Mapped[date] = mapped_column(sa.Date)
    fact_type: Mapped[str] = mapped_column(Text)
    fact_id: Mapped[uuid.UUID] = mapped_column()
    details: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    verified: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class CandidateSkill(Base):
    """Ребро «владеет»: агрегат доверия по навыку; пишет только пересчёт.

    `top_evidence` хранит id доказательств строками (Text[]: единый тип для PostgreSQL и SQLite).
    """

    __tablename__ = "candidate_skills"
    __table_args__ = (sa.Index("ix_candidate_skills_skill_level", "skill_id", "level"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    confidence: Mapped[float] = mapped_column(sa.Float)
    level: Mapped[int] = mapped_column(sa.SmallInteger)
    sources: Mapped[list[str]] = mapped_column(TextArray)
    top_evidence: Mapped[list[str]] = mapped_column(TextArray)
    claimed_only: Mapped[bool]
    derived: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    derived_from: Mapped[uuid.UUID | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
