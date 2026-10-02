"""evidence: доказательства «факт подтверждает навык» (data-model.md §3.3)

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=False),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("details", sa.JSON()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "candidate_id", "skill_id", "source", "fact_type", "fact_id", name="uq_evidence_fact"
        ),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name="ck_evidence_strength"),
    )
    op.create_index("ix_evidence_skill_id", "evidence", ["skill_id"])
    op.create_index("ix_evidence_fact", "evidence", ["fact_type", "fact_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_evidence_candidate_active ON evidence (candidate_id) WHERE is_active"
        )
    else:
        op.create_index("ix_evidence_candidate_active", "evidence", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("evidence")
