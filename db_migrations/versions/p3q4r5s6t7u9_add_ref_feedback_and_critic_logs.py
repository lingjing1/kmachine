"""add reference_feedbacks and critic_verification_logs logs tables

Revision ID: p3q4r5s6t7u9
Revises: r5s6t7u8v9w0
Create Date: 2026-01-15 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'p3q4r5s6t7u9'
down_revision: Union[str, None] = 'r5s6t7u8v9w0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================
    # 1. 創建 reference_feedbacks 表格
    # ========================================
    op.create_table(
        'reference_feedbacks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('error_types', postgresql.ARRAY(sa.String()), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ondelete='CASCADE'),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='rating_range')
    )
    
    op.create_index('idx_reference_feedbacks_chunk', 'reference_feedbacks', ['chunk_id'])
    op.create_index('idx_reference_feedbacks_teacher', 'reference_feedbacks', ['teacher_id'])

    # ========================================
    # 2. 創建 critic_verification_logs 表格
    # ========================================
    op.create_table(
        'critic_verification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('is_supported', sa.Boolean(), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['job_id'], ['orchestration_jobs.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_critic_logs_job', 'critic_verification_logs', ['job_id'])
    op.create_index('idx_critic_logs_chunk', 'critic_verification_logs', ['chunk_id'])


def downgrade() -> None:
    op.drop_table('critic_verification_logs')
    op.drop_table('reference_feedbacks')
