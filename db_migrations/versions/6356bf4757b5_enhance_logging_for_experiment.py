"""enhance_logging_for_experiment

Revision ID: 6356bf4757b5
Revises: 20260304_turn_logs
Create Date: 2026-03-05 14:45:18.339547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6356bf4757b5'
down_revision: Union[str, Sequence[str], None] = '20260304_turn_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 擴充 GENERATED_CONTENTS
    op.add_column('generated_contents', sa.Column('action_type', sa.String(length=50), nullable=True))
    op.add_column('generated_contents', sa.Column('edit_duration_seconds', sa.Integer(), nullable=True))
    op.add_column('generated_contents', sa.Column('final_content_snapshot', sa.JSON(), nullable=True))

    # 2. 擴充 COURSE_CONTENTS
    op.add_column('course_contents', sa.Column('levenshtein_distance', sa.Integer(), nullable=True))
    op.add_column('course_contents', sa.Column('edit_ratio', sa.Float(), nullable=True))
    op.add_column('course_contents', sa.Column('revision_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('course_contents', sa.Column('total_edit_duration_seconds', sa.Integer(), server_default='0', nullable=False))
    op.add_column('course_contents', sa.Column('view_count', sa.Integer(), server_default='0', nullable=False))

    # 3. 建立 MATERIAL_READING_LOGS
    op.create_table(
        'material_reading_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_session_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('course_contents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('course_units.id', ondelete='CASCADE'), nullable=False),
        sa.Column('stay_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('max_scroll_depth', sa.Float(), nullable=True),
        sa.Column('citation_interactions', sa.JSON(), nullable=True),
        sa.Column('exit_action', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    op.create_index('idx_mrl_session', 'material_reading_logs', ['unit_session_id'])

    # 4. 為現有 Log 表增加 unit_session_id
    op.add_column('student_chatbot_turn_logs', sa.Column('unit_session_id', sa.UUID(), nullable=True))
    op.add_column('student_question_logs', sa.Column('unit_session_id', sa.UUID(), nullable=True))
    
    op.create_index('idx_sctl_session', 'student_chatbot_turn_logs', ['unit_session_id'])
    op.create_index('idx_sql_session', 'student_question_logs', ['unit_session_id'])


def downgrade() -> None:
    op.drop_index('idx_sql_session', table_name='student_question_logs')
    op.drop_index('idx_sctl_session', table_name='student_chatbot_turn_logs')
    op.drop_column('student_question_logs', 'unit_session_id')
    op.drop_column('student_chatbot_turn_logs', 'unit_session_id')

    op.drop_index('idx_mrl_session', table_name='material_reading_logs')
    op.drop_table('material_reading_logs')
    
    op.drop_column('course_contents', 'view_count')
    op.drop_column('course_contents', 'total_edit_duration_seconds')
    op.drop_column('course_contents', 'revision_count')
    op.drop_column('course_contents', 'edit_ratio')
    op.drop_column('course_contents', 'levenshtein_distance')
    
    op.drop_column('generated_contents', 'final_content_snapshot')
    op.drop_column('generated_contents', 'edit_duration_seconds')
    op.drop_column('generated_contents', 'action_type')
