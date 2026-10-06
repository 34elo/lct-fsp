"""assessment: регулярные задания `regular_tasks` и ответы `task_submissions` (E25-1).

Revision ID: b1_11
Revises: b1_10
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_11"
down_revision = "b1_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regular_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("profession", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rubric", sa.JSON()),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_regular_tasks_company_id", "regular_tasks", ["company_id"])
    op.create_table(
        "task_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("regular_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("answer", sa.JSON()),
        sa.Column("score", sa.Float()),
        sa.Column("rubric_marks", sa.JSON()),
        sa.Column("scored_by", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", "candidate_id", "round", name="uq_task_submissions_round"),
    )
    op.create_index("ix_task_submissions_task_id", "task_submissions", ["task_id"])
    op.create_index("ix_task_submissions_candidate_id", "task_submissions", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_task_submissions_candidate_id", table_name="task_submissions")
    op.drop_index("ix_task_submissions_task_id", table_name="task_submissions")
    op.drop_table("task_submissions")
    op.drop_index("ix_regular_tasks_company_id", table_name="regular_tasks")
    op.drop_table("regular_tasks")
