from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tg_user_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger)
    username: Mapped[str | None] = mapped_column(Text, default=None)
    linked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, server_default=sa.func.now()
    )
