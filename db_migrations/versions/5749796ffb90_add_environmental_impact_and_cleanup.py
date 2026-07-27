"""add_environmental_impact_and_cleanup

Revision ID: 5749796ffb90
Revises: 648dfcebd9bd
Create Date: 2026-03-06 17:08:17.753235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5749796ffb90'
down_revision: Union[str, Sequence[str], None] = '648dfcebd9bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Upgrade schema."""
    # Add environmental_impact to AGENT_TASKS
    op.add_column('agent_tasks', sa.Column('environmental_impact', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    
    # Add environmental_impact to ORCHESTRATION_JOBS
    op.add_column('orchestration_jobs', sa.Column('environmental_impact', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))
    
    # Remove estimated_carbon_g from ORCHESTRATION_JOBS
    op.drop_column('orchestration_jobs', 'estimated_carbon_g')


def downgrade() -> None:
    """Downgrade schema."""
    # Restore estimated_carbon_g to ORCHESTRATION_JOBS
    op.add_column('orchestration_jobs', sa.Column('estimated_carbon_g', sa.Numeric(), nullable=True))
    
    # Remove environmental_impact from ORCHESTRATION_JOBS
    op.drop_column('orchestration_jobs', 'environmental_impact')
    
    # Remove environmental_impact from AGENT_TASKS
    op.drop_column('agent_tasks', 'environmental_impact')
