"""vacancies, vacancy_skills

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_arr = sa.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "vacancies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("grade_min", sa.Text(), nullable=False),
        sa.Column("grade_max", sa.Text(), nullable=False),
        sa.Column("formats", _arr, nullable=False),
        sa.Column("employment_type", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("salary_from", sa.Integer(), nullable=False),
        sa.Column("salary_to", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("important_qualities", _arr, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("salary_to >= salary_from", name="ck_vacancies_salary"),
        sa.CheckConstraint("status IN ('draft','published','closed')", name="ck_vacancies_status"),
    )
    op.create_index("ix_vacancies_company_status", "vacancies", ["company_id", "status"])
    op.create_table(
        "vacancy_skills",
        sa.Column(
            "vacancy_id",
            sa.Uuid(),
            sa.ForeignKey("vacancies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id"), primary_key=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("min_level", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.create_index("ix_vacancy_skills_skill", "vacancy_skills", ["skill_id"])


def downgrade() -> None:
    op.drop_index("ix_vacancy_skills_skill", table_name="vacancy_skills")
    op.drop_table("vacancy_skills")
    op.drop_index("ix_vacancies_company_status", table_name="vacancies")
    op.drop_table("vacancies")
