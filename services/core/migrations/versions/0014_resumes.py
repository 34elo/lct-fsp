"""resumes, experience, education, candidates.claimed_soft (data-model.md §3.2)

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_arr = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")
_cand = "candidates.user_id"


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey(_cand, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text()),
        sa.Column("parsed", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued','parsing','parsed','confirmed','failed')", name="ck_resumes_status"
        ),
    )
    op.create_index("ix_resumes_candidate", "resumes", ["candidate_id", "created_at"])
    op.create_table(
        "experience",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey(_cand, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("company", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("description", sa.Text()),
        sa.Column("skill_ids", _arr, nullable=False),
        sa.Column("is_commercial", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.Text(), nullable=False),
    )
    op.create_index("ix_experience_candidate_id", "experience", ["candidate_id"])
    op.create_table(
        "education",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey(_cand, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("institution", sa.Text()),
        sa.Column("degree", sa.Text()),
        sa.Column("field", sa.Text()),
        sa.Column("year_end", sa.Integer()),
    )
    op.create_index("ix_education_candidate_id", "education", ["candidate_id"])
    with op.batch_alter_table("candidates") as b:
        b.add_column(sa.Column("claimed_soft", _arr))


def downgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        b.drop_column("claimed_soft")
    op.drop_table("education")
    op.drop_table("experience")
    op.drop_table("resumes")
