"""skills.skill_type и roles.is_profession: типы навыков и профессии теста (E21-1).

Revision ID: b1_01
Revises: b2_04
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_01"
down_revision = "b2_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("skills") as batch:
        batch.add_column(sa.Column("skill_type", sa.Text()))
    with op.batch_alter_table("roles") as batch:
        batch.add_column(
            sa.Column("is_profession", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("roles") as batch:
        batch.drop_column("is_profession")
    with op.batch_alter_table("skills") as batch:
        batch.drop_column("skill_type")
