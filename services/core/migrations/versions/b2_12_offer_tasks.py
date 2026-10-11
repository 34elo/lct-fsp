"""Задача в приглашении

Revision ID: b2_12
Revises: b2_11
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_12"
down_revision = "b2_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_tasks",
        sa.Column(
            "offer_id", sa.Uuid(), sa.ForeignKey("offers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default=""),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip


def downgrade() -> None:
    op.drop_table("offer_tasks")
