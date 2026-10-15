"""add quota_period_start to users (monthly quota reset)

Revision ID: 0004
Revises: 0002
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('quota_period_start', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'quota_period_start')
