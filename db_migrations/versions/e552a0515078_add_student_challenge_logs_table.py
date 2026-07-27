"""add student_challenge_logs table

Revision ID: e552a0515078
Revises: 20260218_metrics
Create Date: 2026-02-21 01:35:31.957515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e552a0515078'
down_revision: Union[str, Sequence[str], None] = '20260218_metrics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql
    
    op.create_table(
        'student_challenge_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        
        sa.Column('difficulty_level', sa.String(20), nullable=True),
        
        # 答案與評價
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('correctness', sa.String(20), nullable=True),  # 'correct', 'partially_correct', 'incorrect'
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        
        # 時間記錄
        sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledge_points.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unit_id'], ['course_units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "correctness IN ('correct', 'partially_correct', 'incorrect') OR correctness IS NULL",
            name='valid_correctness'
        )
    )
    
    # 索引
    op.create_index('idx_challenge_logs_student', 'student_challenge_logs', ['student_id'])
    op.create_index('idx_challenge_logs_kp', 'student_challenge_logs', ['knowledge_point_id'])
    op.create_index('idx_challenge_logs_question', 'student_challenge_logs', ['question_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('student_challenge_logs')

