"""add job_context to orchestration_jobs

Revision ID: 8387cbbf40d0
Revises: d21186271dc7
Create Date: 2026-02-11 20:04:58.123397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8387cbbf40d0'
down_revision: Union[str, Sequence[str], None] = 'd21186271dc7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column exists (since it might have been added manually)
    conn = op.get_bind()
    res = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='orchestration_jobs' AND column_name='job_context'
    """)).fetchone()
    
    if not res:
        op.add_column('orchestration_jobs', sa.Column('job_context', sa.JSON(), nullable=True, server_default='{}'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orchestration_jobs', 'job_context')
