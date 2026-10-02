"""outbox и inbox

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("event_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=True),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "inbox",
        sa.Column("message_id", sa.Uuid(), primary_key=True),
        sa.Column("handler", sa.String(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inbox")
    op.drop_table("outbox")
