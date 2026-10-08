from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class Company(Base):
    """Компания (data-model.md §3.7). Статусы модерации: `CompanyStatus`."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    inn: Mapped[str | None] = mapped_column(Text, default=None)
    site: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    logo_key: Mapped[str | None] = mapped_column(Text, default=None)
    contacts: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON, default=None)
    direction: Mapped[str | None] = mapped_column(Text, default=None)
    # E32-5a: добровольная метка «компания проверена» (видна кандидатам, если компания verified)
    show_verified_badge: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    responsibility_score: Mapped[float | None] = mapped_column(sa.Float, default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )


class CompanyMember(Base):
    """Участник компании (`role` — `CompanyMemberRole`); пользователь — не более чем в одной."""

    __tablename__ = "company_members"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, unique=True
    )
    role: Mapped[str] = mapped_column(Text)
