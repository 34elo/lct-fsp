"""ФИО кандидата (шифруется): `candidates.full_name_enc` (E36-5, ADR-027)

Revision ID: b2_14
Revises: b2_13
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_14"
down_revision = "b2_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("full_name_enc", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "full_name_enc")
