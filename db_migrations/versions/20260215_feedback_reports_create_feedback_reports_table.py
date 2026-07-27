"""create_feedback_reports_table

Revision ID: 20260215_feedback_reports
Revises: 5c7e328f8348
Create Date: 2026-02-15 17:11:52.015693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260215_feedback_reports'
down_revision: Union[str, Sequence[str], None] = '5c7e328f8348'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Create feedback_reports table."""
    op.create_table(
        'feedback_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_role', sa.String(length=20), nullable=False),
        sa.Column('selected_problems', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )


def downgrade() -> None:
    """Drop feedback_reports table."""
    op.drop_table('feedback_reports')
