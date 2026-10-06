"""salary_basis у вакансий и офферов, отзыв контактов, метка «компания проверена» (E32-5a)

Revision ID: b2_08
Revises: b2_07
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_08"
down_revision = "b2_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("vacancies", "offers"):
        op.add_column(
            table,
            sa.Column("salary_basis", sa.Text(), nullable=False, server_default="gross"),
        )
    op.add_column(
        "contact_reveals", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("show_verified_badge", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    with op.batch_alter_table("companies") as b:
        b.drop_column("show_verified_badge")
    with op.batch_alter_table("contact_reveals") as b:
        b.drop_column("revoked_at")
    for table in ("offers", "vacancies"):
        with op.batch_alter_table(table) as b:
            b.drop_column("salary_basis")
