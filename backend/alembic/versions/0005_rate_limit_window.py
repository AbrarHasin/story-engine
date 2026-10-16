"""rate_limit_window table: Postgres-backed generate rate limit (replaces Redis)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rate_limit_window',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('rate_limit_window')
