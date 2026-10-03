from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.candidates.models import TextArray
from app.identity.models import utcnow


class Notification(Base):
    """Уведомление пользователя (data-model.md §3.12). `channels` ⊂ {web, tg}."""

    __tablename__ = "notifications"
    __table_args__ = (sa.Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(sa.JSON)
    channels: Mapped[list[str]] = mapped_column(TextArray)
    delivered: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
