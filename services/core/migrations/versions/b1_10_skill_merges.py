"""taxonomy: журнал слияний навыков `skill_merges` (E16-5).

Revision ID: b1_10
Revises: b1_09
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_10"
down_revision = "b1_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_merges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("from_skill", sa.Uuid(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("into_skill", sa.Uuid(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("moved", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_skill_merges_from", "skill_merges", ["from_skill"])


def downgrade() -> None:
    op.drop_index("ix_skill_merges_from", table_name="skill_merges")
    op.drop_table("skill_merges")
