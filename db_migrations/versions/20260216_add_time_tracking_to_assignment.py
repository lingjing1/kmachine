"""add started_at and time_spent_minutes to submissions_assignment

Revision ID: 20260216_time_tracking
Revises: 20260215_add_explanation
Create Date: 2026-02-16 14:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260216_time_tracking'
down_revision: Union[str, Sequence[str], None] = '20260215_add_explanation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add started_at and time_spent_minutes to submissions_assignment."""
    op.add_column('submissions_assignment', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('submissions_assignment', sa.Column('time_spent_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove started_at and time_spent_minutes from submissions_assignment."""
    op.drop_column('submissions_assignment', 'time_spent_minutes')
    op.drop_column('submissions_assignment', 'started_at')
