"""Таблицы для логирования показов и реакций (E17-1).

Revision ID: 0023
Revises: 0022

impressions: логирование показов кандидатов в выдаче при поиске/подборе.
rec_feedback: реакции работодателя на показ (открыть, выделить, отклонить, отправить оффер).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "impressions",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("context_type", sa.Text(), nullable=False),  # vacancy | search | similar
        sa.Column("context_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("features", _JSON, nullable=True),
        sa.Column("model_version", sa.Text()),
        sa.Column(
            "shown_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.user_id"]),
    )
    op.create_index(
        "ix_impressions_company_shown_at",
        "impressions",
        ["company_id", "shown_at"],
        postgresql_ops={"shown_at": "DESC"},
    )

    op.create_table(
        "rec_feedback",
        sa.Column("id", _ID, primary_key=True, autoincrement=True),
        sa.Column("impression_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),  # open | dwell | shortlist | dismiss | offer
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["impression_id"], ["impressions.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.user_id"]),
    )
    op.create_index("ix_rec_feedback_impression_id", "rec_feedback", ["impression_id"])
    op.create_index("ix_rec_feedback_session_id", "rec_feedback", ["session_id"])


def downgrade() -> None:
    op.drop_table("rec_feedback")
    op.drop_table("impressions")
