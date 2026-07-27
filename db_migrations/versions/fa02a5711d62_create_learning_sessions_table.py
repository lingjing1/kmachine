"""create_learning_sessions_table

Revision ID: fa02a5711d62
Revises: b7f2929a5a62
Create Date: 2026-03-05 19:59:48.782340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa02a5711d62'
down_revision: Union[str, Sequence[str], None] = 'b7f2929a5a62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 建立 Session 主表
    op.create_table(
        'student_learning_sessions',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('course_units.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_completed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('context_data', sa.JSON(), nullable=True)
    )
    op.create_index('idx_sls_user_unit', 'student_learning_sessions', ['user_id', 'unit_id'])


def downgrade() -> None:
    op.drop_table('student_learning_sessions')
