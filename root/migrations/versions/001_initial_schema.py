"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2025-08-16 07:48:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenants table
    op.create_table('tenants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=True),
        sa.Column('sla_config', sa.JSON(), nullable=True),
        sa.Column('billing_config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create order_events table
    op.create_table('order_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_id', sa.String(length=128), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant', 'source', 'event_id', name='uq_event')
    )
    
    # Create indexes for order_events
    op.create_index('ix_order_events_tenant', 'order_events', ['tenant'])
    op.create_index('ix_order_events_event_type', 'order_events', ['event_type'])
    op.create_index('ix_order_events_order_id', 'order_events', ['order_id'])
    op.create_index('ix_order_events_correlation_id', 'order_events', ['correlation_id'])
    op.create_index('ix_order_events_tenant_order_occurred', 'order_events', ['tenant', 'order_id', 'occurred_at'])
    op.create_index('ix_order_events_tenant_created', 'order_events', ['tenant', 'created_at'])

    # Create exceptions table
    op.create_table('exceptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('reason_code', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('ai_label', sa.String(length=32), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('ops_note', sa.Text(), nullable=True),
        sa.Column('client_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('context_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for exceptions
    op.create_index('ix_exceptions_tenant', 'exceptions', ['tenant'])
    op.create_index('ix_exceptions_order_id', 'exceptions', ['order_id'])
    op.create_index('ix_exceptions_reason_code', 'exceptions', ['reason_code'])
    op.create_index('ix_exceptions_correlation_id', 'exceptions', ['correlation_id'])
    op.create_index('ix_exceptions_tenant_status', 'exceptions', ['tenant', 'status'])
    op.create_index('ix_exceptions_tenant_reason', 'exceptions', ['tenant', 'reason_code'])
    op.create_index('ix_exceptions_tenant_created', 'exceptions', ['tenant', 'created_at'])

    # Create invoices table
    op.create_table('invoices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=128), nullable=False),
        sa.Column('invoice_number', sa.String(length=64), nullable=True),
        sa.Column('billable_ops', sa.JSON(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('invoice_date', sa.DateTime(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for invoices
    op.create_index('ix_invoices_tenant', 'invoices', ['tenant'])
    op.create_index('ix_invoices_order_id', 'invoices', ['order_id'])
    op.create_index('ix_invoices_tenant_status', 'invoices', ['tenant', 'status'])
    op.create_index('ix_invoices_tenant_created', 'invoices', ['tenant', 'created_at'])

    # Create invoice_adjustments table
    op.create_table('invoice_adjustments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=False),
        sa.Column('delta_cents', sa.Integer(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('ai_generated', sa.Boolean(), nullable=False),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for invoice_adjustments
    op.create_index('ix_adjustments_tenant', 'invoice_adjustments', ['tenant'])
    op.create_index('ix_adjustments_tenant_reason', 'invoice_adjustments', ['tenant', 'reason'])
    op.create_index('ix_adjustments_tenant_created', 'invoice_adjustments', ['tenant', 'created_at'])

    # Create dlq table
    op.create_table('dlq',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('error_class', sa.String(length=64), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('source_operation', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for dlq
    op.create_index('ix_dlq_tenant', 'dlq', ['tenant'])
    op.create_index('ix_dlq_correlation_id', 'dlq', ['correlation_id'])
    op.create_index('ix_dlq_tenant_status', 'dlq', ['tenant', 'status'])
    op.create_index('ix_dlq_tenant_created', 'dlq', ['tenant', 'created_at'])
    op.create_index('ix_dlq_next_retry', 'dlq', ['next_retry_at'])


def downgrade() -> None:
    op.drop_table('dlq')
    op.drop_table('invoice_adjustments')
    op.drop_table('invoices')
    op.drop_table('exceptions')
    op.drop_table('order_events')
    op.drop_table('tenants')
