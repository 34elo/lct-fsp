"""Интерес как первый шаг контакта: отметки времени фазы интереса у офферов (E33-1, ADR-026)

Revision ID: b2_09
Revises: b2_08
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_09"
down_revision = "b2_08"
branch_labels = None
depends_on = None

_INTEREST = "status IN ('interest','interest_opened')"


def upgrade() -> None:
    for col in ("interest_at", "interest_opened_at", "invited_at"):
        op.add_column("offers", sa.Column(col, sa.DateTime(timezone=True), nullable=True))
    # недельный лимит интересов компании
    op.create_index("ix_offers_company_interest", "offers", ["company_id", "interest_at"])
    # cron истечения интересов (у `sent|viewed` свой частичный индекс из 0019)
    op.create_index(
        "ix_offers_interest_expires", "offers", ["status", "expires_at"],
        postgresql_where=sa.text(_INTEREST), sqlite_where=sa.text(_INTEREST),
    )  # fmt: skip


def downgrade() -> None:
    op.drop_index("ix_offers_interest_expires", table_name="offers")
    op.drop_index("ix_offers_company_interest", table_name="offers")
    with op.batch_alter_table("offers") as b:
        for col in ("invited_at", "interest_opened_at", "interest_at"):
            b.drop_column(col)
