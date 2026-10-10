"""Заказы LLM-заданий из админки (E43-9): `family_orders`.

Revision ID: b1_18
Revises: b1_17
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_18"
down_revision = "b1_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "family_orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("skill", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("count", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.JSON(), nullable=False),
        sa.Column("slugs", sa.JSON(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_family_orders_created", "family_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_family_orders_created", table_name="family_orders")
    op.drop_table("family_orders")
