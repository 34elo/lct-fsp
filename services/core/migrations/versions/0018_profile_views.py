"""profile_views (data-model.md §3.8)

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_views",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True, autoincrement=True,
        ),
        sa.Column(
            "candidate_id", sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("company_id", sa.Uuid()),
        sa.Column("viewer_user_id", sa.Uuid()),
        sa.Column("source", sa.Text()),
        sa.Column("vacancy_id", sa.Uuid()),
        sa.Column(
            "viewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip
    op.create_index(
        "ix_profile_views_candidate_viewed", "profile_views",
        ["candidate_id", sa.text("viewed_at DESC")],
    )  # fmt: skip


def downgrade() -> None:
    op.drop_index("ix_profile_views_candidate_viewed", table_name="profile_views")
    op.drop_table("profile_views")
