"""analytics_events с месячными партициями (metrics.md §2.4)

Revision ID: 0022
Revises: 0021

PostgreSQL: таблица партиционирована по `ts`, PK `(id, ts)`, партиции на предыдущий,
текущий и два следующих месяца; дальше партиции создаёт `analytics.service.ensure_partition`
при записи. SQLite (тесты): обычная таблица.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _months() -> list[tuple[int, int]]:
    now = datetime.now(UTC)
    base = now.year * 12 + now.month - 1
    return [divmod(base + d, 12) for d in (-1, 0, 1, 2)]


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE TABLE analytics_events (
              id          bigserial,
              ts          timestamptz NOT NULL,
              event       text NOT NULL,
              actor       text,
              role        text,
              session_id  text,
              channel     text,
              run_id      uuid,
              app_version text,
              props       jsonb NOT NULL DEFAULT '{}',
              PRIMARY KEY (id, ts)
            ) PARTITION BY RANGE (ts)
            """
        )
        for y, m0 in _months():
            m = m0 + 1
            ny, nm = (y + (m == 12), m % 12 + 1)
            op.execute(
                f"CREATE TABLE analytics_events_{y}_{m:02d} PARTITION OF analytics_events "
                f"FOR VALUES FROM ('{y}-{m:02d}-01 00:00:00+00') "
                f"TO ('{ny}-{nm:02d}-01 00:00:00+00')"
            )
        op.execute("CREATE INDEX ix_analytics_events_event_ts ON analytics_events (event, ts)")
        op.execute("CREATE INDEX ix_analytics_events_actor_ts ON analytics_events (actor, ts)")
        op.execute(
            "CREATE INDEX ix_analytics_events_run ON analytics_events (run_id) "
            "WHERE run_id IS NOT NULL"
        )
        return
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text()),
        sa.Column("role", sa.Text()),
        sa.Column("session_id", sa.Text()),
        sa.Column("channel", sa.Text()),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("app_version", sa.Text()),
        sa.Column("props", _JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_analytics_events_event_ts", "analytics_events", ["event", "ts"])
    op.create_index("ix_analytics_events_actor_ts", "analytics_events", ["actor", "ts"])


def downgrade() -> None:
    op.execute("DROP TABLE analytics_events")
