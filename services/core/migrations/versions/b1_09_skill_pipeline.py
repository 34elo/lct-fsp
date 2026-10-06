"""taxonomy: журнал решений конвейера навыков `skill_mentions` и черновики карточек (E16-4).

Revision ID: b1_09
Revises: b1_08
"""

import sqlalchemy as sa
from alembic import op

revision = "b1_09"
down_revision = "b1_08"
branch_labels = None
depends_on = None

_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "skill_mentions",
        sa.Column("id", _id, primary_key=True, autoincrement=True),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("norm", sa.Text(), nullable=False),
        sa.Column("context", sa.Text()),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id")),
        sa.Column("relation", sa.Text()),
        sa.Column("scores", sa.JSON()),
        sa.Column("model_version", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_skill_mentions_norm", "skill_mentions", ["norm"])
    op.create_table(
        "skill_card_drafts",
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("card", sa.JSON(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("skill_card_drafts")
    op.drop_index("ix_skill_mentions_norm", table_name="skill_mentions")
    op.drop_table("skill_mentions")
