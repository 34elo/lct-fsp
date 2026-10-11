"""offers: приглашение без вакансии

`vacancy_id` необязателен; поля `title`, `description`, `contact_method`, `initiator`.

Revision ID: b2_02
Revises: b2_01
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_02"
down_revision = "b2_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as b:
        b.alter_column("vacancy_id", existing_type=sa.Uuid(), nullable=True)
        b.add_column(sa.Column("title", sa.Text(), nullable=True))
        b.add_column(sa.Column("description", sa.Text(), nullable=True))
        b.add_column(sa.Column("contact_method", sa.Text(), nullable=True))
        b.add_column(sa.Column("initiator", sa.Text(), nullable=False, server_default="employer"))


def downgrade() -> None:
    # Строки без вакансии не удаляем молча: downgrade с ними упадёт на NOT NULL.
    with op.batch_alter_table("offers") as b:
        b.drop_column("initiator")
        b.drop_column("contact_method")
        b.drop_column("description")
        b.drop_column("title")
        b.alter_column("vacancy_id", existing_type=sa.Uuid(), nullable=False)
