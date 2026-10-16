"""convert naive timestamp columns to TIMESTAMP WITH TIME ZONE

Stored values were written as naive UTC, so they are reinterpreted with
`AT TIME ZONE 'UTC'`: every row keeps the same UTC instant.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

# (table, column, nullable) for every column created as naive DateTime in 0001.
# users.quota_period_start (0004) is already timezone-aware.
COLUMNS = [
    ('users', 'created_at', False),
    ('personalities', 'created_at', False),
    ('personalities', 'updated_at', False),
    ('stories', 'created_at', False),
    ('stories', 'completed_at', True),
    ('payments', 'created_at', False),
    ('payments', 'confirmed_at', True),
]


def upgrade() -> None:
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table, column,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table, column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
