"""add explanation to student_question_logs

Revision ID: 20260215_add_explanation
Revises: 20260215_feedback_reports
Create Date: 2026-02-15 22:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260215_add_explanation'
down_revision: Union[str, Sequence[str], None] = '20260215_feedback_reports'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add explanation column to student_question_logs table."""
    op.add_column('student_question_logs', sa.Column('explanation', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove explanation column from student_question_logs table."""
    op.drop_column('student_question_logs', 'explanation')
