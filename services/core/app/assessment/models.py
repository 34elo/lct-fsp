"""Таблицы модуля `assessment`.

`grades` — текущий подтверждённый грейд по профессии: пишет только модуль теста (и `seed_grade`),
остальные модули читают через `service.py`. `surveys`, `families`, `attempts`, `responses` —
внутренние таблицы теста.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
    # standard | express — экспресс-грейд показывается меткой
    mode: Mapped[str] = mapped_column(Text, default="standard", server_default="standard")
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="SET NULL"), default=None
    )
    confirmed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    next_change_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (sa.Index("ix_grades_profession_grade", "profession", "grade"),)


class Survey(Base):
    """Опрос кандидата; история — новые строки."""

    __tablename__ = "surveys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    industry: Mapped[str | None] = mapped_column(Text, default=None)
    profession: Mapped[str] = mapped_column(Text)
    stack: Mapped[list] = mapped_column(sa.JSON, default=list)
    formats: Mapped[list] = mapped_column(sa.JSON, default=list)
    salary_from: Mapped[int | None] = mapped_column(default=None)
    salary_to: Mapped[int | None] = mapped_column(default=None)
    declared_grade: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)

    __table_args__ = (sa.Index("ix_surveys_candidate_created", "candidate_id", "created_at"),)


class FamilyRow(Base):
    """Семейство заданий в банке: статус, сложность `b`, статистика."""

    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # code | spec | mutation | llm | fsp
    skill_id: Mapped[uuid.UUID] = mapped_column()  # taxonomy.service.skill_id(slug)
    skill_type: Mapped[str] = mapped_column(Text)  # SkillType
    level: Mapped[int] = mapped_column(sa.SmallInteger)
    b: Mapped[float] = mapped_column(sa.Float)
    n: Mapped[int] = mapped_column(default=0, server_default="0")
    anchor: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    spec: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    key_status: Mapped[str] = mapped_column(Text, default="approved", server_default="approved")
    author_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    company_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    competition_id: Mapped[str | None] = mapped_column(Text, default=None)  # source = fsp
    ai_solvable: Mapped[float] = mapped_column(sa.Float, default=0.0, server_default="0")
    stats: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        sa.Index("ix_families_status_type", "status", "skill_type"),
        sa.Index("ix_families_competition", "competition_id"),
    )


class Attempt(Base):
    """Попытка теста на профессию и заявленный грейд."""

    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    profession: Mapped[str] = mapped_column(Text)
    declared_grade: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, default="main")  # main | bonus
    mode: Mapped[str] = mapped_column(Text, default="standard", server_default="standard")
    status: Mapped[str] = mapped_column(Text, default="active")  # active|passed|failed|abandoned
    plan: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    theta: Mapped[float | None] = mapped_column(sa.Float, default=None)
    se: Mapped[float | None] = mapped_column(sa.Float, default=None)
    llr: Mapped[float] = mapped_column(sa.Float, default=0.0)
    integrity: Mapped[float] = mapped_column(sa.Float, default=1.0)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)

    __table_args__ = (
        sa.Index("ix_attempts_candidate_status", "candidate_id", "status"),
        sa.Index("ix_attempts_cand_prof_finished", "candidate_id", "profession", "finished_at"),
    )


class Response(Base):
    """Выданное задание и ответ. Ключа нет: задание пересобирается из `(family_id, seed)`."""

    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column()
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"))
    seed: Mapped[int] = mapped_column(sa.BigInteger)
    is_pilot: Mapped[bool] = mapped_column(default=False)
    answer: Mapped[Any] = mapped_column(sa.JSON, default=None)
    score: Mapped[float | None] = mapped_column(sa.Float, default=None)
    rt_ms: Mapped[int | None] = mapped_column(default=None)
    telemetry: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)

    __table_args__ = (
        sa.UniqueConstraint("attempt_id", "seq", name="uq_responses_attempt_seq"),
        sa.UniqueConstraint("attempt_id", "family_id", name="uq_responses_attempt_family"),
    )


class RegularTask(Base):
    """Регулярное задание компании кандидатам её категории."""

    __tablename__ = "regular_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column()
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"))
    profession: Mapped[str] = mapped_column(Text)  # ProfessionSlug
    grade: Mapped[str] = mapped_column(Text)  # TestGrade
    title: Mapped[str] = mapped_column(Text)
    rubric: Mapped[list | None] = mapped_column(sa.JSON, default=None)  # пункты, только `open`
    period_days: Mapped[int] = mapped_column(default=14, server_default="14")
    status: Mapped[str] = mapped_column(Text, default="draft")  # draft | open | closed
    round: Mapped[int] = mapped_column(default=0, server_default="0")  # номер рассылки
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )  # последняя рассылка
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)


class TaskSubmission(Base):
    """Ответ кандидата на регулярное задание; один на (задание, кандидат, рассылка)."""

    __tablename__ = "task_submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regular_tasks.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), index=True
    )
    round: Mapped[int] = mapped_column()
    seed: Mapped[int] = mapped_column(sa.BigInteger)
    answer: Mapped[Any] = mapped_column(sa.JSON, default=None)
    score: Mapped[float | None] = mapped_column(sa.Float, default=None)  # None — ждёт оценки
    rubric_marks: Mapped[list | None] = mapped_column(sa.JSON, default=None)
    scored_by: Mapped[str | None] = mapped_column(Text, default=None)  # auto|llm_draft|employer
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    scored_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)

    __table_args__ = (
        sa.UniqueConstraint("task_id", "candidate_id", "round", name="uq_task_submissions_round"),
    )


class FamilyOrder(Base):
    """Заказ админа на LLM-задания: навык × `kind` × уровень × `count` → черновики.

    `status`: `queued` (команда в outbox) → `running` (ml-worker взял) → `done` | `failed`.
    `created` — сколько черновиков легло в `families`, `rejected` — отбраковка по причинам.
    """

    __tablename__ = "family_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    skill: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(sa.SmallInteger)
    count: Mapped[int] = mapped_column(sa.SmallInteger)
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")
    created: Mapped[int] = mapped_column(default=0, server_default="0")
    rejected: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    slugs: Mapped[list] = mapped_column(sa.JSON, default=list)
    model: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (sa.Index("ix_family_orders_created", "created_at"),)
