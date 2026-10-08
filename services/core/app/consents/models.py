from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.identity.models import utcnow


class Consent(Base):
    __tablename__ = "consents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    type: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), primary_key=True, default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
