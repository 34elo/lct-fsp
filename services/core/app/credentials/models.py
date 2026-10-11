from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class IssuedCredential(Base):
    """Выданный Open Badge 3.0: подписанный VC целиком в `credential`."""

    __tablename__ = "issued_credentials"
    __table_args__ = (sa.Index("ix_issued_credentials_candidate", "candidate_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    profession: Mapped[str] = mapped_column(Text)
    grade: Mapped[str] = mapped_column(Text)
    profile_version: Mapped[int] = mapped_column(default=0)
    credential: Mapped[dict] = mapped_column(sa.JSON)
    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    revoke_reason: Mapped[str | None] = mapped_column(Text, default=None)
