"""Роль вакансии — профессия из справочника (E39-17)

Демо-вакансия «AI Engineer» раньше хранила `ml` (контракт не знал `ai_engineer`):
переносим на профессию из справочника, если она там есть.

Revision ID: b2_15
Revises: b2_14
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_15"
down_revision = "b2_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE vacancies SET role = 'ai_engineer' "
            "WHERE role = 'ml' AND lower(title) LIKE 'ai engineer%' "
            "AND EXISTS (SELECT 1 FROM roles WHERE slug = 'ai_engineer' AND is_profession = :t)"
        ).bindparams(t=True)
    )


def downgrade() -> None:
    pass
