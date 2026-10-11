"""candidates: primary_role, roles, primary_stack

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_ARR = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.add_column(sa.Column("primary_role", sa.Text()))
        b.add_column(sa.Column("roles", sa.JSON()))
        b.add_column(sa.Column("primary_stack", _ARR))


def downgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.drop_column("primary_stack")
        b.drop_column("roles")
        b.drop_column("primary_role")
