"""companies: добавить контакты и направление деятельности

Revision ID: b2_01
Revises: s0_02
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_01"
down_revision = "s0_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "contacts",
            sa.JSON(),
            nullable=True,
            comment="Контакты: {name, email, phone, telegram}",
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "direction",
            sa.Text(),
            nullable=True,
            comment="Направление деятельности компании",
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "direction")
    op.drop_column("companies", "contacts")
