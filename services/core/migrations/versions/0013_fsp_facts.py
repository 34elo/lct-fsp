"""fsp_*: участники, соревнования, результаты, разряды, команды (data-model.md §3.5)

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_cand = "candidates.user_id"


def upgrade() -> None:
    op.create_table(
        "fsp_participants",
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey(_cand, ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("participant_id", sa.Text(), nullable=False, unique=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "fsp_competitions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text()),
        sa.Column("discipline", sa.Text()),
        sa.Column("level", sa.Text()),
        sa.Column("format", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("status", sa.Text()),
        sa.Column("tracks", sa.JSON()),
        sa.Column("registration_url", sa.Text()),
        sa.Column("participants_total", sa.Integer()),
        sa.Column("raw", sa.JSON()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
    )
    # competition_id без FK: результат может прийти раньше календаря
    op.create_table(
        "fsp_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "candidate_id", sa.Uuid(), sa.ForeignKey(_cand, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("participant_id", sa.Text(), nullable=False),
        sa.Column("competition_id", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("discipline", sa.Text()),
        sa.Column("team_id", sa.Text()),
        sa.Column("team_role", sa.Text()),
        sa.Column("place", sa.Integer()),
        sa.Column("participants_total", sa.Integer()),
        sa.Column("score", sa.Float()),
        sa.Column("track", sa.Text()),
        sa.Column("date", sa.Date()),
        sa.Column("raw", sa.JSON()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "participant_id", "competition_id", "stage", name="uq_fsp_results_participant"
        ),
    )
    op.create_index("ix_fsp_results_candidate", "fsp_results", ["candidate_id"])
    op.create_table(
        "fsp_ranks",
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey(_cand, ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("discipline", sa.Text(), primary_key=True),
        sa.Column("rank", sa.Text(), nullable=False),
        sa.Column("assigned_at", sa.Date()),
    )
    op.create_table(
        "fsp_teams",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("competition_id", sa.Text()),
    )
    op.create_table(
        "fsp_team_members",
        sa.Column("team_id", sa.Text(), sa.ForeignKey("fsp_teams.id"), primary_key=True),
        sa.Column("participant_id", sa.Text(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid()),  # заполнен, если участник есть на платформе
        sa.Column("role", sa.Text()),
    )
    op.create_index("ix_fsp_team_members_participant", "fsp_team_members", ["participant_id"])


def downgrade() -> None:
    op.drop_index("ix_fsp_team_members_participant", table_name="fsp_team_members")
    op.drop_table("fsp_team_members")
    op.drop_table("fsp_teams")
    op.drop_table("fsp_ranks")
    op.drop_index("ix_fsp_results_candidate", table_name="fsp_results")
    op.drop_table("fsp_results")
    op.drop_table("fsp_competitions")
    op.drop_table("fsp_participants")
