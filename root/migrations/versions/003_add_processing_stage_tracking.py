"""Add processing stage tracking and data completeness validation

Revision ID: 003
Revises: 002
Create Date: 2025-08-20 09:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add processing stage tracking and data completeness tables."""
    
    # Create order_processing_stages table
    op.create_table(
        'order_processing_stages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant', sa.String(64), sa.ForeignKey('tenants.name'), nullable=False, index=True),
        sa.Column('order_id', sa.String(128), nullable=False, index=True),
        sa.Column('stage_name', sa.String(64), nullable=False),
        sa.Column('stage_status', sa.String(16), nullable=False, server_default='PENDING'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stage_data', postgresql.JSONB(), nullable=True),
        sa.Column('dependencies_met', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        
        # Constraints
        sa.UniqueConstraint('tenant', 'order_id', 'stage_name', name='uq_processing_stage'),
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_processing_stages_tenant_order', 'order_processing_stages', ['tenant', 'order_id'])
    op.create_index('ix_processing_stages_status', 'order_processing_stages', ['tenant', 'stage_name', 'stage_status'])
    op.create_index('ix_processing_stages_eligible', 'order_processing_stages', ['tenant', 'stage_status', 'dependencies_met'])
    
    # Create data_completeness_checks table
    op.create_table(
        'data_completeness_checks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant', sa.String(64), sa.ForeignKey('tenants.name'), nullable=False, index=True),
        sa.Column('order_id', sa.String(128), nullable=False, index=True),
        sa.Column('check_type', sa.String(64), nullable=False),
        sa.Column('check_status', sa.String(16), nullable=False, server_default='PENDING'),
        sa.Column('check_result', postgresql.JSONB(), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        
        # Constraints
        sa.UniqueConstraint('tenant', 'order_id', 'check_type', name='uq_completeness_check'),
    )
    
    # Create indexes for data completeness checks
    op.create_index('ix_completeness_checks_tenant_order', 'data_completeness_checks', ['tenant', 'order_id'])
    op.create_index('ix_completeness_checks_status', 'data_completeness_checks', ['tenant', 'check_type', 'check_status'])


def downgrade():
    """Remove processing stage tracking tables."""
    
    # Drop indexes
    op.drop_index('ix_completeness_checks_status', table_name='data_completeness_checks')
    op.drop_index('ix_completeness_checks_tenant_order', table_name='data_completeness_checks')
    op.drop_index('ix_processing_stages_eligible', table_name='order_processing_stages')
    op.drop_index('ix_processing_stages_status', table_name='order_processing_stages')
    op.drop_index('ix_processing_stages_tenant_order', table_name='order_processing_stages')
    
    # Drop tables
    op.drop_table('data_completeness_checks')
    op.drop_table('order_processing_stages')
