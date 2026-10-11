"""companies, company_members

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inn", sa.Text()),
        sa.Column("site", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("logo_key", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("responsibility_score", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending','verified','rejected','blocked')", name="ck_companies_status"
        ),
    )
    op.create_index("ix_companies_status", "companies", ["status"])
    op.create_table(
        "company_members",
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_company_members_user"),
        sa.CheckConstraint("role IN ('admin','member')", name="ck_company_members_role"),
    )


def downgrade() -> None:
    op.drop_table("company_members")
    op.drop_index("ix_companies_status", table_name="companies")
    op.drop_table("companies")
