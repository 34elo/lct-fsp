"""candidate_links: связи людей по командам ФСП

Revision ID: b2_04
Revises: b2_03
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_04"
down_revision = "b2_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_links",
        sa.Column(
            "candidate_a",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "candidate_b",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("context_id", sa.Text(), primary_key=True),
    )
    op.create_index("ix_candidate_links_a", "candidate_links", ["candidate_a"])
    op.create_index("ix_candidate_links_b", "candidate_links", ["candidate_b"])


def downgrade() -> None:
    op.drop_index("ix_candidate_links_b", table_name="candidate_links")
    op.drop_index("ix_candidate_links_a", table_name="candidate_links")
    op.drop_table("candidate_links")
