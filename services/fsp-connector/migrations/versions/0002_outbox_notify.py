"""outbox: NOTIFY для relay и частичный индекс неотправленных

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from fsp_platform.outbox import OUTBOX_NOTIFY_DDL, OUTBOX_NOTIFY_DROP

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
        sqlite_where=sa.text("published_at IS NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        for stmt in OUTBOX_NOTIFY_DDL:
            op.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for stmt in OUTBOX_NOTIFY_DROP:
            op.execute(stmt)
    op.drop_index("ix_outbox_unpublished", table_name="outbox")
