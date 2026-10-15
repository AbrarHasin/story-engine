"""stories.embedding: TEXT -> vector(384)

0001 created the column as TEXT while the model declares a pgvector Vector.
Nothing ever wrote to it, so existing values are discarded. 384 matches the
local sentence-transformers/all-MiniLM-L6-v2 embedding model.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE stories ALTER COLUMN embedding TYPE vector(384) USING NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE stories ALTER COLUMN embedding TYPE text USING NULL")
