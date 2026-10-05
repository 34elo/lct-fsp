"""users.email_verified_at: подтверждение email (blocks.md §4.6).

Revision ID: s0_02
Revises: s0_01
"""

import sqlalchemy as sa
from alembic import op

revision = "s0_02"
down_revision = "s0_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
