"""offers, offer_events

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("vacancy_id", sa.Uuid(), sa.ForeignKey("vacancies.id"), nullable=False),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey("candidates.user_id", ondelete="SET NULL")
        ),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("salary_from", sa.Integer(), nullable=False),
        sa.Column("salary_to", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="sent"),
        sa.Column("decline_reason", sa.Text()),
        sa.Column("decline_comment", sa.Text()),
        sa.Column("awaiting_reply_from", sa.Text()),
        sa.Column("match_snapshot", sa.JSON()),
        sa.Column("below_candidate_min", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("team_offer_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True)),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("vacancy_id", "candidate_id", name="uq_offers_vacancy_candidate"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_offers_company_idem"),
        sa.CheckConstraint("salary_to >= salary_from", name="ck_offers_salary_range"),
    )
    op.create_index(
        "ix_offers_candidate_created", "offers", ["candidate_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_offers_company_created", "offers", ["company_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_offers_status_expires", "offers", ["status", "expires_at"],
        postgresql_where=sa.text("status IN ('sent','viewed')"),
        sqlite_where=sa.text("status IN ('sent','viewed')"),
    )  # fmt: skip
    op.create_table(
        "offer_events",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True, autoincrement=True,
        ),
        sa.Column(
            "offer_id", sa.Uuid(), sa.ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )  # fmt: skip
    op.create_index("ix_offer_events_offer", "offer_events", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_events_offer", table_name="offer_events")
    op.drop_table("offer_events")
    op.drop_index("ix_offers_status_expires", table_name="offers")
    op.drop_index("ix_offers_company_created", table_name="offers")
    op.drop_index("ix_offers_candidate_created", table_name="offers")
    op.drop_table("offers")
