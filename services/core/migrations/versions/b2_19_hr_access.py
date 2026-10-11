"""Доступ HR без почты: временный пароль, смена при первом входе, журнал.

`users.must_change_password` — вход временным паролем, до смены доступны только `/me` и
`/auth/password/initial`; `users.temp_password_expires_at` — срок временного пароля (72 ч);
`users.managed_by_company_id` — аккаунт создан владельцем этой компании (ему можно выдать
новый пароль). `company_access_log` — журнал: кто, кого, когда (создал, сбросил, отозвал).

Revision ID: b2_19
Revises: b2_18
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_19"
down_revision = "b2_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users", sa.Column("temp_password_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("managed_by_company_id", sa.Uuid(), nullable=True))
    op.create_table(
        "company_access_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "target_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_email", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip
    op.create_index("ix_company_access_log_company_id", "company_access_log", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_company_access_log_company_id", "company_access_log")
    op.drop_table("company_access_log")
    op.drop_column("users", "managed_by_company_id")
    op.drop_column("users", "temp_password_expires_at")
    op.drop_column("users", "must_change_password")
