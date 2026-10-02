"""taxonomy: skills, aliases, relations, roles, disciplines, scoring_config (data-model.md §3.4)

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("grp", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("merged_into", sa.Uuid(), sa.ForeignKey("skills.id")),
        sa.Column("support_candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("support_vacancies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("testable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "skill_aliases",
        sa.Column("alias_norm", sa.Text(), primary_key=True),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
    )
    op.create_index("ix_skill_aliases_skill_id", "skill_aliases", ["skill_id"])
    op.create_table(
        "skill_relations",
        sa.Column("skill_a", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("skill_b", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("weight BETWEEN 0 AND 1", name="ck_skill_relations_w"),
    )
    op.create_index("ix_skill_relations_b_kind", "skill_relations", ["skill_b", "kind"])
    op.create_table(
        "skill_distinct",
        sa.Column("skill_a", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("skill_b", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
    )
    op.create_table(
        "skill_blocklist",
        sa.Column("norm", sa.Text(), primary_key=True),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "roles",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
    )
    op.create_table(
        "role_skills",
        sa.Column("role", sa.Text(), sa.ForeignKey("roles.slug"), primary_key=True),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="seed"),
    )
    op.create_table(
        "disciplines",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
    )
    op.create_table(
        "discipline_skill_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("discipline", sa.Text(), sa.ForeignKey("disciplines.slug"), nullable=False),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("track", sa.Text()),
    )
    op.create_index(
        "uq_discipline_skill_rules",
        "discipline_skill_rules",
        ["discipline", "skill_id", sa.text("coalesce(track, '')")],
        unique=True,
    )
    op.create_table(
        "scoring_config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for t in (
        "scoring_config",
        "discipline_skill_rules",
        "disciplines",
        "role_skills",
        "roles",
        "skill_blocklist",
        "skill_distinct",
        "skill_relations",
        "skill_aliases",
        "skills",
    ):
        op.drop_table(t)
