"""Встречный сигнал: кандидат показал интерес к компании

Revision ID: b2_11
Revises: b2_10
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_11"
down_revision = "b2_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_interests",
        sa.Column(
            "candidate_id", sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip
    op.create_index(
        "ix_candidate_interests_company", "candidate_interests", ["company_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_interests_company", table_name="candidate_interests")
    op.drop_table("candidate_interests")
