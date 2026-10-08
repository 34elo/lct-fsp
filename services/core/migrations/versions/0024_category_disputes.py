"""Оспаривание категории кандидатом (E4-6).

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_disputes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claimed_role", sa.Text(), nullable=False),
        sa.Column("claimed_grade", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_category_disputes_candidate_id", "category_disputes", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("category_disputes")
