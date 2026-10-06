"""families: `competition_id` — соревнование ФСП, из которого взято задание (E32-6, ADR-025).

Участникам этого соревнования задание не показывается (assessment.md §4, «задачи ФСП в банке»).

Revision ID: b1_14
Revises: b1_13
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_14"
down_revision = "b1_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("families", sa.Column("competition_id", sa.Text(), nullable=True))
    op.create_index("ix_families_competition", "families", ["competition_id"])


def downgrade() -> None:
    op.drop_index("ix_families_competition", table_name="families")
    with op.batch_alter_table("families") as b:
        b.drop_column("competition_id")
