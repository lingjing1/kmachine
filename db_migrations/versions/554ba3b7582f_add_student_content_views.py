"""add_student_content_views

Revision ID: 554ba3b7582f
Revises: a6b7c8d9e0f1
Create Date: 2026-07-28 10:55:10.852851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '554ba3b7582f'
down_revision: Union[str, Sequence[str], None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_content_views',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('first_viewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('student_id', 'content_id', name='uq_student_content_view'),
    )
    op.create_index(
        'idx_student_content_views_lookup',
        'student_content_views',
        ['student_id', 'content_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_student_content_views_lookup', table_name='student_content_views')
    op.drop_table('student_content_views')