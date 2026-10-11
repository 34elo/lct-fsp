"""live_runs: живые прогоны

Revision ID: b2_03
Revises: b2_02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2_03"
down_revision = "b2_02"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "live_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("tasks", _JSON, nullable=False),
        sa.Column("actor", sa.Text()),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("sus_answers", _JSON),
        sa.Column("sus_score", sa.Float()),
        sa.Column("category_agree", sa.Boolean()),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("ix_live_runs_actor", "live_runs", ["actor"])


def downgrade() -> None:
    op.drop_index("ix_live_runs_actor", table_name="live_runs")
    op.drop_table("live_runs")
