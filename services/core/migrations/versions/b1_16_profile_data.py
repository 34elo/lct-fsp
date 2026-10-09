"""Профиль кандидата (E39-15): скрытые навыки и ссылки (шифруются)

`candidates.hidden_skills` — slug навыков, которые кандидат убрал из профиля: работодатель их не
видит, в подборе они по-прежнему участвуют. `candidates.links_enc` — ссылки кандидата (GitHub,
портфолио), шифруются как контакты и видны только владельцу.

Revision ID: b1_16
Revises: b2_15
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_16"
down_revision = "b2_15"
branch_labels = None
depends_on = None

_arr = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column("candidates", sa.Column("hidden_skills", _arr, nullable=True))
    op.add_column("candidates", sa.Column("links_enc", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "links_enc")
    op.drop_column("candidates", "hidden_skills")
