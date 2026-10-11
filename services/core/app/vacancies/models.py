from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.candidates.models import TextArray
from app.identity.models import utcnow


class Vacancy(Base):
    """Вакансия с обязательной вилкой «от–до» и навыками."""

    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    grade_min: Mapped[str] = mapped_column(Text)
    grade_max: Mapped[str] = mapped_column(Text)
    formats: Mapped[list[str]] = mapped_column(TextArray)
    employment_type: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, default=None)
    salary_from: Mapped[int]
    salary_to: Mapped[int]
    salary_basis: Mapped[str] = mapped_column(Text, default="gross", server_default="gross")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    important_qualities: Mapped[list[str]] = mapped_column(TextArray, default=list)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    # демо-данные (seed, жюри): не в статистике, сбрасываются `demo-reset`
    is_demo: Mapped[bool] = mapped_column(default=False, server_default=sa.false())


class VacancySkill(Base):
    __tablename__ = "vacancy_skills"

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    required: Mapped[bool]
    min_level: Mapped[int] = mapped_column(sa.SmallInteger, default=2, server_default="2")
    weight: Mapped[float] = mapped_column(sa.Float, default=1.0, server_default="1.0")
