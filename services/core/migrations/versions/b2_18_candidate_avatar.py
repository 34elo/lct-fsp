"""Аватар кандидата: `candidates.avatar_key` — ключ файла в MinIO (E41-12)

Revision ID: b2_18
Revises: b2_17
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_18"
down_revision = "b2_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("avatar_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "avatar_key")
