"""Реестр ФСП: мероприятия, участники, результаты, заявки на привязку

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "fsp_reg_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("discipline", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
    )
    op.create_table(
        "fsp_reg_participants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email_norm", sa.String(), nullable=True),
        sa.Column("phone_norm", sa.String(), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
    )
    op.create_index("ix_fsp_reg_participants_email_norm", "fsp_reg_participants", ["email_norm"])
    op.create_index("ix_fsp_reg_participants_phone_norm", "fsp_reg_participants", ["phone_norm"])
    op.create_table(
        "fsp_reg_results",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "participant_id",
            sa.String(),
            sa.ForeignKey("fsp_reg_participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("fsp_reg_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("team", sa.String(), nullable=True),
        sa.Column("updated_at", _TS, nullable=False),
        sa.UniqueConstraint("participant_id", "event_id"),
    )
    op.create_index("ix_fsp_reg_results_participant_id", "fsp_reg_results", ["participant_id"])
    op.create_index("ix_fsp_reg_results_event_id", "fsp_reg_results", ["event_id"])
    op.create_table(
        "fsp_link_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("event", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("participant_id", sa.String(), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.Column("decided_at", _TS, nullable=True),
    )
    op.create_index("ix_fsp_link_requests_candidate_id", "fsp_link_requests", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("fsp_link_requests")
    op.drop_table("fsp_reg_results")
    op.drop_table("fsp_reg_participants")
    op.drop_table("fsp_reg_events")
