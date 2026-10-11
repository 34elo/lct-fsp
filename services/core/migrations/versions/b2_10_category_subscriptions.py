"""Подписки компаний на категории и подошедшие кандидаты

Revision ID: b2_10
Revises: b2_09
"""

import sqlalchemy as sa
from alembic import op

revision = "b2_10"
down_revision = "b2_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profession", sa.Text(), nullable=False),
        sa.Column("grades", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("formats", sa.JSON(), nullable=False),
        sa.Column("only_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip
    op.create_index(
        "ix_category_subscriptions_company_id", "category_subscriptions", ["company_id"]
    )
    op.create_index("ix_category_subs_profession", "category_subscriptions", ["profession"])
    op.create_table(
        "category_subscription_hits",
        sa.Column(
            "subscription_id", sa.Uuid(),
            sa.ForeignKey("category_subscriptions.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey("candidates.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )  # fmt: skip


def downgrade() -> None:
    op.drop_table("category_subscription_hits")
    op.drop_index("ix_category_subs_profession", "category_subscriptions")
    op.drop_index("ix_category_subscriptions_company_id", "category_subscriptions")
    op.drop_table("category_subscriptions")
