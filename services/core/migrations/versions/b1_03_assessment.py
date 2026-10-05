"""assessment: surveys, families, attempts, responses + FK grades.attempt_id (E22-1).

Revision ID: b1_03
Revises: b1_02
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_03"
down_revision = "b1_02"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "surveys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("industry", sa.Text()),
        sa.Column("profession", sa.Text(), nullable=False),
        sa.Column("stack", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("formats", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("salary_from", sa.Integer()),
        sa.Column("salary_to", sa.Integer()),
        sa.Column("declared_grade", sa.Text()),
        _ts("created_at"),
    )
    op.create_index("ix_surveys_candidate_created", "surveys", ["candidate_id", "created_at"])

    op.create_table(
        "families",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),  # code | spec | mutation | llm
        sa.Column("skill_id", sa.Uuid(), nullable=False),  # стабильный id навыка (uuid5 по slug)
        sa.Column("skill_type", sa.Text(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("b", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anchor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("spec", sa.JSON()),
        sa.Column("key_status", sa.Text(), nullable=False, server_default="approved"),
        sa.Column("author_id", sa.Uuid()),
        sa.Column("company_id", sa.Uuid()),
        sa.Column("ai_solvable", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stats", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_families_status_type", "families", ["status", "skill_type"])

    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profession", sa.Text(), nullable=False),
        sa.Column("declared_grade", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False, server_default="main"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("plan", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("theta", sa.Float()),
        sa.Column("se", sa.Float()),
        sa.Column("llr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("integrity", sa.Float(), nullable=False, server_default="1.0"),
        _ts("started_at"),
        _ts("finished_at", nullable=True),
    )
    op.create_index("ix_attempts_candidate_status", "attempts", ["candidate_id", "status"])

    op.create_table(
        "responses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("is_pilot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answer", sa.JSON()),
        sa.Column("score", sa.Float()),
        sa.Column("rt_ms", sa.Integer()),
        sa.Column("telemetry", sa.JSON()),
        _ts("created_at"),
        _ts("answered_at", nullable=True),
        sa.UniqueConstraint("attempt_id", "seq", name="uq_responses_attempt_seq"),
        sa.UniqueConstraint("attempt_id", "family_id", name="uq_responses_attempt_family"),
    )

    with op.batch_alter_table("grades") as batch:
        batch.create_foreign_key(
            "fk_grades_attempt_id", "attempts", ["attempt_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("grades") as batch:
        batch.drop_constraint("fk_grades_attempt_id", type_="foreignkey")
    op.drop_table("responses")
    op.drop_index("ix_attempts_candidate_status", table_name="attempts")
    op.drop_table("attempts")
    op.drop_index("ix_families_status_type", table_name="families")
    op.drop_table("families")
    op.drop_index("ix_surveys_candidate_created", table_name="surveys")
    op.drop_table("surveys")
