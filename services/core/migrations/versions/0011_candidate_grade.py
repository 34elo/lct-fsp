"""candidates: grade_*, experience_months, team_signals (data-model.md §3.2, ml.md §5)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_COLS = (
    ("grade", sa.Text()),
    ("grade_score", sa.Float()),
    ("grade_confidence", sa.Float()),
    ("grade_breakdown", sa.JSON()),
    ("grade_next", sa.JSON()),
    ("experience_months", sa.Integer()),
    ("team_signals", sa.JSON()),
)


def upgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        for name, typ in _COLS:
            b.add_column(sa.Column(name, typ))


def downgrade() -> None:
    with op.batch_alter_table("candidates") as b:
        for name, _ in reversed(_COLS):
            b.drop_column(name)
