from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    grp: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    source: Mapped[str] = mapped_column(Text)
    merged_into: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.id"), default=None)
    support_candidates: Mapped[int] = mapped_column(default=0, server_default="0")
    support_vacancies: Mapped[int] = mapped_column(default=0, server_default="0")
    testable: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    # fundamental | hard | thinking | business | soft | experience (assessment.md §2)
    skill_type: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    alias_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"))
    source: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(default=None)


class SkillRelation(Base):
    __tablename__ = "skill_relations"
    __table_args__ = (sa.CheckConstraint("weight BETWEEN 0 AND 1", name="ck_skill_relations_w"),)

    skill_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    skill_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)  # adjacent | parent
    weight: Mapped[float]
    source: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SkillDistinct(Base):
    """«Точно разные» (Java ≠ JavaScript): хранится одна строка на пару, skill_a < skill_b."""

    __tablename__ = "skill_distinct"

    skill_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    skill_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)


class SkillBlocklist(Base):
    __tablename__ = "skill_blocklist"

    norm: Mapped[str] = mapped_column(Text, primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class Role(Base):
    __tablename__ = "roles"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # профессия теста (assessment.md §2); остальные роли — только для подсказок и поиска
    is_profession: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    # профессия видна в опросе и выдаче (ADR-027 п.1); скрытая хранит данные, но не предлагается
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())


class RoleSkill(Base):
    __tablename__ = "role_skills"

    role: Mapped[str] = mapped_column(ForeignKey("roles.slug"), primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    weight: Mapped[float]
    source: Mapped[str] = mapped_column(Text, default="seed", server_default="seed")


class Discipline(Base):
    __tablename__ = "disciplines"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class DisciplineSkillRule(Base):
    __tablename__ = "discipline_skill_rules"
    __table_args__ = (
        sa.Index(
            "uq_discipline_skill_rules",
            "discipline",
            "skill_id",
            sa.func.coalesce(sa.column("track"), ""),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    discipline: Mapped[str] = mapped_column(ForeignKey("disciplines.slug"))
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"))
    weight: Mapped[float]
    track: Mapped[str | None] = mapped_column(Text, default=None)


class ScoringConfig(Base):
    """Версионируемые настройки (ключ `taxonomy` хранит версию и хеш справочника)."""

    __tablename__ = "scoring_config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(sa.JSON)
    version: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SkillMention(Base):
    """Журнал и кеш решений конвейера навыков ml (skills.md §3.3): ключ кеша — `norm`."""

    __tablename__ = "skill_mentions"
    __table_args__ = (sa.Index("ix_skill_mentions_norm", "norm"),)

    id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True
    )
    raw: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text, default=None)  # resume|vacancy|repo|query
    decision: Mapped[str] = mapped_column(Text)  # alias|fuzzy|new|same_pending|rejected
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.id"), default=None)
    relation: Mapped[str | None] = mapped_column(Text, default=None)
    scores: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    model_version: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class SkillCardDraftRow(Base):
    """Черновик карточки нового навыка от ml (E16-4). В `data/skills/cards` — после ревью."""

    __tablename__ = "skill_card_drafts"

    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    card: Mapped[dict] = mapped_column(sa.JSON)  # форма `SkillCard`, schema_version 1
    model: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class SkillMerge(Base):
    """Журнал слияний (skills.md §6): по `moved` слияние откатывается (разделение)."""

    __tablename__ = "skill_merges"
    __table_args__ = (sa.Index("ix_skill_merges_from", "from_skill"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_skill: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"))
    into_skill: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id"))
    actor: Mapped[str] = mapped_column(Text)  # admin:<user_id> | pipeline
    moved: Mapped[dict] = mapped_column(sa.JSON)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    reverted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
