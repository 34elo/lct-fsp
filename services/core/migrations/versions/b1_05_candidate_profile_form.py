"""candidates: контакты (Fernet) и желаемые роли для ручной формы профиля (E20-4).

Revision ID: b1_05
Revises: b1_04
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_05"
down_revision = "b1_04"
branch_labels = None
depends_on = None

_arr = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column("candidates", sa.Column("contacts_enc", sa.LargeBinary()))
    op.add_column("candidates", sa.Column("desired_roles", _arr))


def downgrade() -> None:
    op.drop_column("candidates", "desired_roles")
    op.drop_column("candidates", "contacts_enc")
