"""credentials: таблица issued_credentials для Open Badge 3.0

Revision ID: b2_07
Revises: b2_06
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_07"
down_revision = "b2_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issued_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profession", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credential", sa.JSON(), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_issued_credentials_candidate", "issued_credentials", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_issued_credentials_candidate", table_name="issued_credentials")
    op.drop_table("issued_credentials")
