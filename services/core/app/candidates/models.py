from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow

TextArray = sa.ARRAY(Text()).with_variant(sa.JSON(), "sqlite")
DEFAULT_VISIBILITY = {
    "companies": False,
    "education": False,
    "repos": False,
    "teams": True,
    "public_profile": False,
}


class Candidate(Base):
    """Анкета кандидата (data-model.md §3.2). Вычисляемое: категория (E4-3), грейд — E4-4."""

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
    # слияние пересчётов (graph.md §4.4)
    recompute_requested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )
    recomputed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
