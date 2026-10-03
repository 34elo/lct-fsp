"""Модели для логирования показов и реакций (E17-1)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fsp_platform.db import Base
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UUID as SQLUuid,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB


class Impression(Base):
    """Логирование показа кандидата в выдаче поиска или подборки."""

    __tablename__ = "impressions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(SQLUuid, ForeignKey("companies.id"), nullable=False)
    user_id = Column(SQLUuid, nullable=False)  # работодатель, отправивший запрос
    session_id = Column(String, nullable=False)  # UUID сессии поиска/подборки
    context_type = Column(String, nullable=False)  # vacancy | search | similar
    context_id = Column(String, nullable=False)  # ID вакансии или строка поиска
    candidate_id = Column(SQLUuid, ForeignKey("candidates.user_id"), nullable=False)
    position = Column(SmallInteger, nullable=False)  # позиция в выдаче (1-based)
    score = Column(Float, nullable=False)  # итоговый скор совпадения
    features = Column(JSON, nullable=True)  # признаки для ML: {relevance, trust, ...}
    model_version = Column(String)  # версия модели скоринга
    shown_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    __table_args__ = (
        Index("ix_impressions_company_shown_at", "company_id", "shown_at", postgresql_ops={"shown_at": "DESC"}),
    )


class RecFeedback(Base):
    """Логирование реакции работодателя на показ кандидата."""

    __tablename__ = "rec_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    impression_id = Column(BigInteger, ForeignKey("impressions.id"), nullable=False)
    company_id = Column(SQLUuid, ForeignKey("companies.id"), nullable=False)
    user_id = Column(SQLUuid, nullable=False)  # работодатель
    session_id = Column(String, nullable=False)  # сессия, в которой произошла реакция
    candidate_id = Column(SQLUuid, ForeignKey("candidates.user_id"), nullable=False)
    event = Column(String, nullable=False)  # open | dwell | shortlist | dismiss | offer
    reason = Column(Text)  # причина отклонения или комментарий
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    __table_args__ = (
        Index("ix_rec_feedback_impression_id", "impression_id"),
        Index("ix_rec_feedback_session_id", "session_id"),
    )
