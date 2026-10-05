from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

EMAIL_TYPE = Text().with_variant(CITEXT(), "postgresql")


def utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(EMAIL_TYPE, unique=True, default=None)
    password_hash: Mapped[str | None] = mapped_column(Text, default=None)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    # подтверждение email (blocks.md §4.6); поток кода — E20-1
    email_verified_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), default=None
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)  # sha256
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)


class EmailVerification(Base):
    """Активный код подтверждения email (E20-1): одна строка на пользователя."""

    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code_hash: Mapped[str] = mapped_column(Text)  # sha256(user_id:code), сам код не храним
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
