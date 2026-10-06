"""Представление graph_edges: UNION ALL рёбер графа для визуализации и выгрузки (graph.md §4.1).

Revision ID: b1_08
Revises: b1_05
"""

from alembic import op

revision = "b1_08"
down_revision = "b1_05"
branch_labels = None
depends_on = None

# Переносимый SQL (PostgreSQL и SQLite): CAST вместо `::`.
_VIEW = """
CREATE VIEW graph_edges AS
SELECT 'candidate' AS src_type, e.candidate_id AS src_id, e.fact_type AS dst_type,
       e.fact_id AS dst_id, 'has_fact' AS kind, CAST(NULL AS REAL) AS weight,
       e.observed_at AS observed_at
  FROM evidence e WHERE e.is_active
UNION ALL
SELECT e.fact_type, e.fact_id, 'skill', e.skill_id, 'confirms', e.strength, e.observed_at
  FROM evidence e WHERE e.is_active
UNION ALL
SELECT 'candidate', cs.candidate_id, 'skill', cs.skill_id, 'owns', cs.confidence,
       CAST(cs.updated_at AS DATE)
  FROM candidate_skills cs
UNION ALL
SELECT 'skill', r.skill_a, 'skill', r.skill_b, r.kind, r.weight, CAST(NULL AS DATE)
  FROM skill_relations r
UNION ALL
SELECT 'vacancy', vs.vacancy_id, 'skill', vs.skill_id, 'requires', vs.weight, CAST(NULL AS DATE)
  FROM vacancy_skills vs
"""


def upgrade() -> None:
    op.execute(_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS graph_edges")
