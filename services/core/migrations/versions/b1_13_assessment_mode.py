"""attempts, grades: режим теста `mode` — standard | express.

Revision ID: b1_13
Revises: b1_12
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_13"
down_revision = "b1_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attempts", sa.Column("mode", sa.Text(), nullable=False, server_default="standard")
    )
    op.add_column("grades", sa.Column("mode", sa.Text(), nullable=False, server_default="standard"))


def downgrade() -> None:
    with op.batch_alter_table("grades") as b:
        b.drop_column("mode")
    with op.batch_alter_table("attempts") as b:
        b.drop_column("mode")
