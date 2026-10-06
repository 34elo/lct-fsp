"""needs: добавить shortlist для уточнения фильтров без потери подборки (E23-5)

Revision ID: b2_06
Revises: b2_05
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_06"
down_revision = "b2_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "needs",
        sa.Column("shortlist", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("needs", "shortlist")
