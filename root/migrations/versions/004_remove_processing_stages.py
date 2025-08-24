"""Remove processing stage tables

Revision ID: 004
Revises: 003
Create Date: 2025-08-24 05:42:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove processing stage tables as part of orchestration simplification."""
    # Drop tables in correct order (child tables first)
    op.drop_table('data_completeness_checks')
    op.drop_table('order_processing_stages')


def downgrade() -> None:
    """Recreate processing stage tables if rollback is needed."""
    # Recreate order_processing_stages table
    op.create_table('order_processing_stages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('stage_name', sa.String(length=64), nullable=False),
        sa.Column('stage_status', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stage_data', sa.JSON(), nullable=True),
        sa.Column('dependencies_met', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant'], ['tenants.name'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant', 'order_id', 'stage_name', name='uq_processing_stage')
    )
    op.create_index('ix_processing_stages_tenant_order', 'order_processing_stages', ['tenant', 'order_id'], unique=False)
    op.create_index('ix_processing_stages_status', 'order_processing_stages', ['tenant', 'stage_name', 'stage_status'], unique=False)
    op.create_index('ix_processing_stages_eligible', 'order_processing_stages', ['tenant', 'stage_status', 'dependencies_met'], unique=False)
    op.create_index(op.f('ix_order_processing_stages_order_id'), 'order_processing_stages', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_processing_stages_tenant'), 'order_processing_stages', ['tenant'], unique=False)

    # Recreate data_completeness_checks table
    op.create_table('data_completeness_checks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('check_type', sa.String(length=64), nullable=False),
        sa.Column('check_status', sa.String(length=16), nullable=False),
        sa.Column('check_result', sa.JSON(), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant'], ['tenants.name'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant', 'order_id', 'check_type', name='uq_completeness_check')
    )
    op.create_index('ix_completeness_checks_tenant_order', 'data_completeness_checks', ['tenant', 'order_id'], unique=False)
    op.create_index('ix_completeness_checks_status', 'data_completeness_checks', ['tenant', 'check_type', 'check_status'], unique=False)
    op.create_index(op.f('ix_data_completeness_checks_order_id'), 'data_completeness_checks', ['order_id'], unique=False)
    op.create_index(op.f('ix_data_completeness_checks_tenant'), 'data_completeness_checks', ['tenant'], unique=False)
