"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255)),
        sa.Column('plan', sa.Enum('free','pro','enterprise', name='plantier'), nullable=False, server_default='free'),
        sa.Column('stories_this_month', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'personalities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('voice', sa.Text()),
        sa.Column('tone', sa.String(100)),
        sa.Column('reading_level', sa.String(50)),
        sa.Column('banned_words', postgresql.JSON()),
        sa.Column('locale', sa.String(10), nullable=False, server_default='en'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'stories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('personality_id', postgresql.UUID(as_uuid=True)),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('tonality', sa.String(100), nullable=False, server_default='neutral'),
        sa.Column('audience', sa.String(100), nullable=False, server_default='general'),
        sa.Column('length', sa.String(50), nullable=False, server_default='medium'),
        sa.Column('locale', sa.String(10), nullable=False, server_default='en'),
        sa.Column('research', sa.Text()),
        sa.Column('light_side', sa.Text()),
        sa.Column('dark_side', sa.Text()),
        sa.Column('facts', sa.Text()),
        sa.Column('narrative', sa.Text()),
        sa.Column('final_output', sa.Text()),
        sa.Column('status', sa.Enum('pending','running','completed','failed', name='storystatus'), nullable=False),
        sa.Column('tokens_input', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_output', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('langgraph_run_id', sa.String(255)),
        sa.Column('embedding', sa.Text()),  # pgvector handled via model
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['personality_id'], ['personalities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tran_id', sa.String(255), nullable=False),
        sa.Column('val_id', sa.String(255)),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='BDT'),
        sa.Column('plan', sa.Enum('free','pro','enterprise', name='plantier'), nullable=False),
        sa.Column('status', sa.Enum('initiated','confirmed','failed','cancelled', name='paymentstatus'), nullable=False),
        sa.Column('ipn_payload', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tran_id'),
    )


def downgrade() -> None:
    op.drop_table('payments')
    op.drop_table('stories')
    op.drop_table('personalities')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS paymentstatus")
    op.execute("DROP TYPE IF EXISTS storystatus")
    op.execute("DROP TYPE IF EXISTS plantier")
