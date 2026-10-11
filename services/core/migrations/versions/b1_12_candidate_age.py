"""candidates: возрастная группа и согласие родителя для кандидатов 15–17 лет.

Revision ID: b1_12
Revises: b1_11
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_12"
down_revision = "b1_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("age_group", sa.Text()))
    op.add_column("candidates", sa.Column("parent_consent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("candidates", "parent_consent_at")
    op.drop_column("candidates", "age_group")
