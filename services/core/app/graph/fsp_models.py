"""Нормализованные факты ФСП в core (data-model.md §3.5). Пишет только `fsp_ingest`."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


class FspParticipant(Base):
    __tablename__ = "fsp_participants"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[str] = mapped_column(Text, unique=True)
    verified: Mapped[bool]


class FspCompetitionRow(Base):
    __tablename__ = "fsp_competitions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    discipline: Mapped[str | None] = mapped_column(Text, default=None)
    level: Mapped[str | None] = mapped_column(Text, default=None)
    format: Mapped[str | None] = mapped_column(Text, default=None)
    region: Mapped[str | None] = mapped_column(Text, default=None)
    start_date: Mapped[date | None] = mapped_column(default=None)
    end_date: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str | None] = mapped_column(Text, default=None)
    tracks: Mapped[list | None] = mapped_column(sa.JSON, default=None)
    registration_url: Mapped[str | None] = mapped_column(Text, default=None)
    participants_total: Mapped[int | None] = mapped_column(default=None)
    raw: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)


class FspResultRow(Base):
    """Вершина-факт «результат ФСП»; `id` детерминирован по (participant, competition, stage)."""

    __tablename__ = "fsp_results"
    __table_args__ = (
        sa.UniqueConstraint(
            "participant_id", "competition_id", "stage", name="uq_fsp_results_participant"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE")
    )
    participant_id: Mapped[str] = mapped_column(Text)
    competition_id: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    discipline: Mapped[str | None] = mapped_column(Text, default=None)
    team_id: Mapped[str | None] = mapped_column(Text, default=None)
    team_role: Mapped[str | None] = mapped_column(Text, default=None)
    place: Mapped[int | None] = mapped_column(default=None)
    participants_total: Mapped[int | None] = mapped_column(default=None)
    score: Mapped[float | None] = mapped_column(default=None)
    track: Mapped[str | None] = mapped_column(Text, default=None)
    date: Mapped[date | None] = mapped_column(default=None)
    raw: Mapped[dict | None] = mapped_column(sa.JSON, default=None)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())


class FspRankRow(Base):
    __tablename__ = "fsp_ranks"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True
    )
    discipline: Mapped[str] = mapped_column(Text, primary_key=True)
    rank: Mapped[str] = mapped_column(Text)
    assigned_at: Mapped[date | None] = mapped_column(default=None)


class FspTeamRow(Base):
    __tablename__ = "fsp_teams"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, default=None)
    competition_id: Mapped[str | None] = mapped_column(Text, default=None)


class FspTeamMember(Base):
    __tablename__ = "fsp_team_members"

    team_id: Mapped[str] = mapped_column(ForeignKey("fsp_teams.id"), primary_key=True)
    participant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    role: Mapped[str | None] = mapped_column(Text, default=None)
