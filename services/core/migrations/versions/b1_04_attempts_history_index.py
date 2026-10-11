"""assessment: индекс истории и кулдаунов попыток.

Revision ID: b1_04
Revises: b1_03
"""

from alembic import op

revision = "b1_04"
down_revision = "b1_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_attempts_cand_prof_finished",
        "attempts",
        ["candidate_id", "profession", "finished_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_attempts_cand_prof_finished", table_name="attempts")
