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
    """Компания. Статусы модерации: `CompanyStatus`."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    inn: Mapped[str | None] = mapped_column(Text, default=None)
    site: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    logo_key: Mapped[str | None] = mapped_column(Text, default=None)
    contacts: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON, default=None)
    direction: Mapped[str | None] = mapped_column(Text, default=None)
    # добровольная метка «компания проверена» (видна кандидатам, если компания verified)
    show_verified_badge: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    responsibility_score: Mapped[float | None] = mapped_column(sa.Float, default=None)
    # демо-данные (seed, жюри): не в статистике, сбрасываются `demo-reset`
    is_demo: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
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


class CompanyInvite(Base):
    """Приглашение в компанию по email: токен ссылки хранится sha256, одноразовый."""

    __tablename__ = "company_invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="member", server_default="member")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)


class CompanyAccessLog(Base):
    """Журнал доступа HR: кто (`actor_id`), кого (`target_*`), что и когда.

    `action`: `created` — владелец создал аккаунт HR, `password_reset` — выдал новый временный
    пароль, `revoked` — отозвал доступ. Пароли в журнал не пишутся.
    """

    __tablename__ = "company_access_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    target_email: Mapped[str | None] = mapped_column(Text, default=None)
    action: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
