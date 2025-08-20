"""Add processing stage tracking models

Revision ID: 003
Revises: 002
Create Date: 2024-12-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create order_processing_stages table
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
    
    # Create indexes for order_processing_stages
    op.create_index('ix_processing_stages_tenant_order', 'order_processing_stages', ['tenant', 'order_id'])
    op.create_index('ix_processing_stages_status', 'order_processing_stages', ['tenant', 'stage_name', 'stage_status'])
    op.create_index('ix_processing_stages_eligible', 'order_processing_stages', ['tenant', 'stage_status', 'dependencies_met'])
    op.create_index(op.f('ix_order_processing_stages_tenant'), 'order_processing_stages', ['tenant'])
    op.create_index(op.f('ix_order_processing_stages_order_id'), 'order_processing_stages', ['order_id'])
    
    # Create data_completeness_checks table
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
    
    # Create indexes for data_completeness_checks
    op.create_index('ix_completeness_checks_tenant_order', 'data_completeness_checks', ['tenant', 'order_id'])
    op.create_index('ix_completeness_checks_status', 'data_completeness_checks', ['tenant', 'check_type', 'check_status'])
    op.create_index(op.f('ix_data_completeness_checks_tenant'), 'data_completeness_checks', ['tenant'])
    op.create_index(op.f('ix_data_completeness_checks_order_id'), 'data_completeness_checks', ['order_id'])
    
    # Set default values for new columns
    op.execute("UPDATE order_processing_stages SET stage_status = 'PENDING' WHERE stage_status IS NULL")
    op.execute("UPDATE order_processing_stages SET retry_count = 0 WHERE retry_count IS NULL")
    op.execute("UPDATE order_processing_stages SET max_retries = 3 WHERE max_retries IS NULL")
    op.execute("UPDATE order_processing_stages SET dependencies_met = false WHERE dependencies_met IS NULL")
    
    op.execute("UPDATE data_completeness_checks SET check_status = 'PENDING' WHERE check_status IS NULL")


def downgrade() -> None:
    # Drop data_completeness_checks table and indexes
    op.drop_index(op.f('ix_data_completeness_checks_order_id'), table_name='data_completeness_checks')
    op.drop_index(op.f('ix_data_completeness_checks_tenant'), table_name='data_completeness_checks')
    op.drop_index('ix_completeness_checks_status', table_name='data_completeness_checks')
    op.drop_index('ix_completeness_checks_tenant_order', table_name='data_completeness_checks')
    op.drop_table('data_completeness_checks')
    
    # Drop order_processing_stages table and indexes
    op.drop_index(op.f('ix_order_processing_stages_order_id'), table_name='order_processing_stages')
    op.drop_index(op.f('ix_order_processing_stages_tenant'), table_name='order_processing_stages')
    op.drop_index('ix_processing_stages_eligible', table_name='order_processing_stages')
    op.drop_index('ix_processing_stages_status', table_name='order_processing_stages')
    op.drop_index('ix_processing_stages_tenant_order', table_name='order_processing_stages')
    op.drop_table('order_processing_stages')
