from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fsp_platform.db import Base
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class AnalyticsEventRow(Base):
    """Продуктовое событие (metrics.md §2.4). В PostgreSQL — партиции по месяцам, PK `(id, ts)`.

    Пишем через Core `insert()`: `id` выдаёт БД (bigserial / rowid в SQLite для тестов).
    """

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), primary_key=True)
    event: Mapped[str] = mapped_column(sa.Text)
    actor: Mapped[str | None] = mapped_column(sa.Text)
    role: Mapped[str | None] = mapped_column(sa.Text)
    session_id: Mapped[str | None] = mapped_column(sa.Text)
    channel: Mapped[str | None] = mapped_column(sa.Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    app_version: Mapped[str | None] = mapped_column(sa.Text)
    props: Mapped[dict] = mapped_column(_JSON, default=dict, server_default="{}")


class LiveRun(Base):
    """Живой прогон (metrics.md §3): приглашение испытателю, задания, SUS.

    `tasks` — список `{id, title, target, count, done_at}`; `actor` — псевдоним испытателя
    (привязывается по токену первого события с `run_id`): по нему серверные события
    (`resume_confirmed`, `shortlisted`…) без `run_id` тоже попадают в прогон.
    """

    __tablename__ = "live_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)
    scenario: Mapped[str] = mapped_column(sa.Text)
    token: Mapped[str] = mapped_column(sa.Text, unique=True)
    tasks: Mapped[list] = mapped_column(_JSON)
    actor: Mapped[str | None] = mapped_column(sa.Text, index=True)
    invited_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    sus_answers: Mapped[list | None] = mapped_column(_JSON)
    sus_score: Mapped[float | None] = mapped_column(sa.Float)
    category_agree: Mapped[bool | None] = mapped_column(sa.Boolean)
    notes: Mapped[str | None] = mapped_column(sa.Text)
