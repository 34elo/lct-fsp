"""needs: потребности работодателя

Revision ID: b2_05
Revises: b2_04
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_05"
down_revision = "b2_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "needs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("grades", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_needs_company", "needs", ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_needs_company", table_name="needs")
    op.drop_table("needs")
