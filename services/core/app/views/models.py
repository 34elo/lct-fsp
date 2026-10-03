from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class ProfileView(Base):
    """Журнал открытия карточки работодателем (data-model.md §3.8, security.md §3)."""

    __tablename__ = "profile_views"
    __table_args__ = (
        sa.Index("ix_profile_views_candidate_viewed", "candidate_id", sa.text("viewed_at DESC")),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                                    primary_key=True, autoincrement=True)  # fmt: skip
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    viewer_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    source: Mapped[str | None] = mapped_column(Text, default=None)
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    viewed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
