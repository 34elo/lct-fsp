"""candidate_skills и поля слияния пересчётов

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_ARR = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.add_column(sa.Column("recompute_requested_at", sa.DateTime(timezone=True)))
        b.add_column(sa.Column("recomputed_at", sa.DateTime(timezone=True)))
    op.create_table(
        "candidate_skills",
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("sources", _ARR, nullable=False),
        sa.Column("top_evidence", _ARR, nullable=False),
        sa.Column("claimed_only", sa.Boolean(), nullable=False),
        sa.Column("derived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("derived_from", sa.Uuid()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_candidate_skills_skill_level", "candidate_skills", ["skill_id", "level"])


def downgrade() -> None:
    op.drop_table("candidate_skills")
    with op.batch_alter_table("candidates") as b:
        b.drop_column("recomputed_at")
        b.drop_column("recompute_requested_at")
