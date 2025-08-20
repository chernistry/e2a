"""Add resolution attempt tracking to exceptions

Revision ID: 002
Revises: 618fd9555930
Create Date: 2025-08-20 07:18:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '618fd9555930'
branch_labels = None
depends_on = None


def upgrade():
    """Add resolution attempt tracking fields to exceptions table."""
    
    # Add new columns for resolution attempt tracking
    op.add_column('exceptions', sa.Column('resolution_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('exceptions', sa.Column('max_resolution_attempts', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('exceptions', sa.Column('last_resolution_attempt_at', sa.DateTime(), nullable=True))
    op.add_column('exceptions', sa.Column('resolution_blocked', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('exceptions', sa.Column('resolution_block_reason', sa.Text(), nullable=True))
    
    # Add index for efficient querying of resolution-eligible exceptions
    op.create_index('ix_exceptions_resolution_eligible', 'exceptions', 
                   ['tenant', 'status', 'resolution_attempts', 'resolution_blocked'])


def downgrade():
    """Remove resolution attempt tracking fields."""
    
    # Drop index
    op.drop_index('ix_exceptions_resolution_eligible', table_name='exceptions')
    
    # Drop columns
    op.drop_column('exceptions', 'resolution_block_reason')
    op.drop_column('exceptions', 'resolution_blocked')
    op.drop_column('exceptions', 'last_resolution_attempt_at')
    op.drop_column('exceptions', 'max_resolution_attempts')
    op.drop_column('exceptions', 'resolution_attempts')
