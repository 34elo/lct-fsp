from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow

TextArray = sa.ARRAY(Text()).with_variant(sa.JSON(), "sqlite")
EMBEDDING_DIM = 1024


class _PgVector(sa.types.UserDefinedType):
    """`vector(N)` из pgvector без отдельной зависимости: значение передаём и читаем текстом."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dim})"

    def bind_expression(self, bindvalue):
        return sa.cast(sa.cast(bindvalue, sa.Text), self)  # текст → vector на стороне PostgreSQL

    def bind_processor(self, dialect):
        return lambda v: None if v is None else "[" + ",".join(repr(float(x)) for x in v) + "]"


class Vector(sa.types.TypeDecorator):
    """Вектор эмбеддинга: pgvector в PostgreSQL, JSON-список в SQLite (тесты)."""

    impl = sa.JSON
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(sa.JSON())

    def process_result_value(self, value, dialect):
        if isinstance(
            value, str
        ):  # pgvector отдаёт «[0.1,0.2]» (asyncpg без кодека отдаёт vector текстом)
            return [float(x) for x in value.strip("[]").split(",") if x]
        return value


DEFAULT_VISIBILITY = {
    "companies": False,
    "education": False,
    "repos": False,
    "teams": True,
    "public_profile": False,
}


class Candidate(Base):
    """Анкета кандидата (data-model.md §3.2). Вычисляемое: категория (E4-3), грейд (E4-4)."""

    __tablename__ = "candidates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    pseudonym: Mapped[str] = mapped_column(Text, unique=True)
    pseudo_id: Mapped[str] = mapped_column(Text, unique=True)  # HMAC(secret, user_id)[:12]
    city: Mapped[str | None] = mapped_column(Text, default=None)
    relocation: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    search_status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    active_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    salary_min: Mapped[int | None] = mapped_column(default=None)
    formats: Mapped[list[str]] = mapped_column(TextArray, default=list)
    employment_types: Mapped[list[str]] = mapped_column(TextArray, default=list)
    visibility: Mapped[dict] = mapped_column(sa.JSON, default=lambda: dict(DEFAULT_VISIBILITY))
    stoplist_company_ids: Mapped[list[str]] = mapped_column(TextArray, default=list)
    profile_version: Mapped[int] = mapped_column(default=0, server_default="0")
    # категория (ml.md §4), считает recompute_profile
    primary_role: Mapped[str | None] = mapped_column(Text, default=None)
    roles: Mapped[list | None] = mapped_column(sa.JSON, default=None)  # [{role, weight}]
    primary_stack: Mapped[list[str] | None] = mapped_column(TextArray, default=None)
    # грейд (ml.md §5), считает recompute_profile
    grade: Mapped[str | None] = mapped_column(Text, default=None)
    grade_score: Mapped[float | None] = mapped_column(sa.Float, default=None)
    grade_confidence: Mapped[float | None] = mapped_column(sa.Float, default=None)
    grade_breakdown: Mapped[list | None] = mapped_column(sa.JSON, default=None)
    grade_next: Mapped[dict | None] = mapped_column(sa.JSON, default=None)  # next_grade + hints
    experience_months: Mapped[int | None] = mapped_column(default=None)
    # смысловой слой (graph.md §4.3): вектор пересчитывается, если sha(profile_text) сменился
    profile_text: Mapped[str | None] = mapped_column(Text, default=None)
    profile_text_sha: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # sha256 текста embedding
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), default=None)
    embedding_model: Mapped[str | None] = mapped_column(Text, default=None)
    team_signals: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    claimed_soft: Mapped[list[str] | None] = mapped_column(TextArray, default=None)
    # ручная форма (E20-4): контакты шифруются Fernet (security.md §3), желаемые роли — slug
    contacts_enc: Mapped[bytes | None] = mapped_column(sa.LargeBinary, default=None)
    desired_roles: Mapped[list[str] | None] = mapped_column(TextArray, default=None)
    # возраст (E32-5b): только группа, дата рождения не собирается; `minor` = 15–17 лет
    age_group: Mapped[str | None] = mapped_column(Text, default=None)  # adult | minor
    parent_consent_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )  # отметка о согласии родителя на обработку ПДн несовершеннолетнего
    # слияние пересчётов (graph.md §4.4)
    recompute_requested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )
    recomputed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)


class CategoryDispute(Base):
    """Оспаривание категории кандидатом; разбирает админ (data-model.md §3.2)."""

    __tablename__ = "category_disputes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), index=True
    )
    claimed_role: Mapped[str] = mapped_column(Text)
    claimed_grade: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
