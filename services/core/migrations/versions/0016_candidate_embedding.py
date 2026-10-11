"""candidates: profile_text, profile_text_sha, embedding vector(1024), embedding_model

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    if pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with op.batch_alter_table("candidates") as b:
        b.add_column(sa.Column("profile_text", sa.Text()))
        b.add_column(sa.Column("profile_text_sha", sa.Text()))
        b.add_column(sa.Column("embedding_model", sa.Text()))
        if not pg:
            b.add_column(sa.Column("embedding", sa.JSON()))
    if pg:
        op.execute("ALTER TABLE candidates ADD COLUMN embedding vector(1024)")
        op.execute(
            "CREATE INDEX ix_candidates_embedding ON candidates "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_candidates_embedding")
    with op.batch_alter_table("candidates") as b:
        for name in ("embedding", "embedding_model", "profile_text_sha", "profile_text"):
            b.drop_column(name)
