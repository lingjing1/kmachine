"""create_class_statistics_table

Revision ID: 5c7e328f8348
Revises: f64a39f5fbe8
Create Date: 2026-02-15 15:08:40.714124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c7e328f8348'
down_revision: Union[str, Sequence[str], None] = 'f64a39f5fbe8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'class_statistics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('course_units.id', ondelete='CASCADE'), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=True),

        # Core: weak KP names list for teacher API
        sa.Column('weak_knowledge_points', sa.JSON(), server_default='[]', nullable=False),

        # Full mastery distribution snapshot per KP
        sa.Column('mastery_distribution', sa.JSON(), server_default='[]', nullable=False),

        # Aggregate counts
        sa.Column('total_students', sa.Integer(), server_default='0', nullable=False),
        sa.Column('preview_completion_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('review_completion_count', sa.Integer(), server_default='0', nullable=False),

        sa.Column('computed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id', 'unit_id', 'stage', name='uq_class_statistics_key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('class_statistics')
