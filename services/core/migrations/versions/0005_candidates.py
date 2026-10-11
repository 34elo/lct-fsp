"""candidates: анкета, предпочтения, видимость, стоп-лист

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_arr = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("pseudonym", sa.Text(), nullable=False, unique=True),
        sa.Column("pseudo_id", sa.Text(), nullable=False, unique=True),
        sa.Column("city", sa.Text()),
        sa.Column("relocation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("search_status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("active_until", sa.DateTime(timezone=True)),
        sa.Column("salary_min", sa.Integer()),
        sa.Column("formats", _arr, nullable=False),
        sa.Column("employment_types", _arr, nullable=False),
        sa.Column("visibility", sa.JSON(), nullable=False),
        sa.Column("stoplist_company_ids", _arr, nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("candidates")
