"""Предложения новых профессий (E41-17): `profession_suggestions`.

Еженедельная задача `taxonomy.professions.suggest` кластеризует навыки вакансий и запросов
работодателей; админ создаёт профессию одной кнопкой или отклоняет (решение запоминается).

Revision ID: b1_17
Revises: b2_19
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_17"
down_revision = "b2_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profession_suggestions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("support_vacancies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("support_needs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nearest_profession", sa.Text(), nullable=True),
        sa.Column("nearest_overlap", sa.Float(), nullable=False, server_default="0"),
        sa.Column("examples", sa.JSON(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="mining"),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("profession", sa.Text(), nullable=True),
        sa.Column(
            "decided_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_profession_suggestions_status", "profession_suggestions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_profession_suggestions_status", table_name="profession_suggestions")
    op.drop_table("profession_suggestions")
