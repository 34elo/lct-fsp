"""Пометка демо-данных `is_demo` (E40-1): пользователи, компании, вакансии, приглашения.

Демо-данные не попадают в статистику лендинга, дашборд ФСП и метрики; `demo-reset` сбрасывает
только их. Бэкфилл: демо — аккаунты `*@demo.fsp.test` (seed, жюри), их компании, вакансии
этих компаний и приглашения, где с одной из сторон демо.

Revision ID: b2_17
Revises: b2_16
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_17"
down_revision = "b2_16"
branch_labels = None
depends_on = None

TABLES = ("users", "companies", "vacancies", "offers")


def upgrade() -> None:
    for t in TABLES:
        op.add_column(
            t, sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute("UPDATE users SET is_demo = true WHERE lower(email) LIKE '%@demo.fsp.test'")
    op.execute(
        "UPDATE companies SET is_demo = true"
        " WHERE id IN (SELECT m.company_id FROM company_members m"
        " JOIN users u ON u.id = m.user_id WHERE u.is_demo)"
    )
    op.execute(
        "UPDATE vacancies SET is_demo = true"
        " WHERE company_id IN (SELECT id FROM companies WHERE is_demo)"
    )
    op.execute(
        "UPDATE offers SET is_demo = true"
        " WHERE company_id IN (SELECT id FROM companies WHERE is_demo)"
        " OR candidate_id IN (SELECT id FROM users WHERE is_demo)"
    )
    for t in TABLES:
        op.create_index(f"ix_{t}_is_demo", t, ["is_demo"], postgresql_where=sa.text("is_demo"))


def downgrade() -> None:
    for t in TABLES:
        op.drop_index(f"ix_{t}_is_demo", t)
        with op.batch_alter_table(t) as b:
            b.drop_column("is_demo")
