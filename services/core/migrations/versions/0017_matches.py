"""matches (data-model.md §3.7)

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column(
            "vacancy_id",
            sa.Uuid(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("candidate_version", sa.Integer(), nullable=False),
        sa.Column("vacancy_version", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_matches_vacancy_score", "matches", ["vacancy_id", sa.text("score DESC")])


def downgrade() -> None:
    op.drop_index("ix_matches_vacancy_score", table_name="matches")
    op.drop_table("matches")
