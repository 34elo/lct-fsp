"""Таблица grades: текущий грейд кандидата по профессии (blocks.md §4.2).

Revision ID: s0_01
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "s0_01"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grades",
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profession", sa.Text(), primary_key=True),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("theta", sa.Float(), nullable=False),
        sa.Column("se", sa.Float()),
        sa.Column("band_position", sa.Float(), nullable=False),
        sa.Column("theta_by_type", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("integrity", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("needs_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("attempt_id", sa.Uuid()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_change_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_grades_valid_until", "grades", ["valid_until"])
    op.create_index("ix_grades_profession_grade", "grades", ["profession", "grade"])


def downgrade() -> None:
    op.drop_index("ix_grades_profession_grade", table_name="grades")
    op.drop_index("ix_grades_valid_until", table_name="grades")
    op.drop_table("grades")
