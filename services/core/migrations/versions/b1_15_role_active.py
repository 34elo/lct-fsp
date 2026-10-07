"""roles.active: скрытые профессии (E36-2, ADR-027 п. 1).

Профессии вне MVP (`ml`, `mobile`, `devops`, `qa`) остаются данными, но скрыты в опросе и UI.
Значения потом поддерживает синхронизация справочника из `data/taxonomy/roles.yaml`.

Revision ID: b1_15
Revises: b2_12
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_15"
down_revision = "b2_12"
branch_labels = None
depends_on = None

_HIDDEN = ("ml", "mobile", "devops", "qa")


def upgrade() -> None:
    with op.batch_alter_table("roles") as batch:
        batch.add_column(
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    roles = sa.table("roles", sa.column("slug", sa.Text()), sa.column("active", sa.Boolean()))
    op.execute(roles.update().where(roles.c.slug.in_(_HIDDEN)).values(active=False))


def downgrade() -> None:
    with op.batch_alter_table("roles") as batch:
        batch.drop_column("active")
