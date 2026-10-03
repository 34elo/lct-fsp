"""offer_messages, contact_reveals, complaints (data-model.md §3.8)

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "offer_id", sa.Uuid(), sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("author_side", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.Uuid()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("channel", sa.Text()),
    )
    op.create_index("ix_offer_messages_offer_created", "offer_messages", ["offer_id", "created_at"])
    op.create_table(
        "contact_reveals",
        sa.Column("offer_id", sa.Uuid(), sa.ForeignKey("offers.id"), primary_key=True),
        sa.Column("candidate_id", sa.Uuid()),
        sa.Column("company_id", sa.Uuid()),
        sa.Column(
            "revealed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "complaints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("offer_id", sa.Uuid(), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("reporter_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("offer_id", "reporter_user_id", name="uq_complaints_offer_reporter"),
    )


def downgrade() -> None:
    op.drop_table("complaints")
    op.drop_table("contact_reveals")
    op.drop_index("ix_offer_messages_offer_created", table_name="offer_messages")
    op.drop_table("offer_messages")
