"""Флаг `roles.is_active`: скрытые профессии

Revision ID: b2_13
Revises: b1_15
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_13"
down_revision = "b1_15"
branch_labels = None
depends_on = None

# Профессии вне охвата MVP: в справочнике остаются, в опросе скрыты (data/taxonomy/roles.yaml)
_HIDDEN = ("ml", "mobile", "devops", "qa")


def upgrade() -> None:
    op.add_column(
        "roles", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    roles = sa.table("roles", sa.column("slug", sa.Text()), sa.column("is_active", sa.Boolean()))
    op.execute(roles.update().where(roles.c.slug.in_(_HIDDEN)).values(is_active=False))


def downgrade() -> None:
    op.drop_column("roles", "is_active")
