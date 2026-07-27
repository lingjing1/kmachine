"""add_experiment_stats_indexes

Revision ID: 55c56739386d
Revises: 4fc5fbccacd6
Create Date: 2026-03-19 15:33:48.422771

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55c56739386d'
down_revision: Union[str, Sequence[str], None] = '4fc5fbccacd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_scd_student_course', 'student_chatbot_dialogs', ['student_id', 'course_id'])
    op.create_index('idx_sctl_student_course', 'student_chatbot_turn_logs', ['student_id', 'course_id'])
    op.create_index('idx_sql_student_course', 'student_question_logs', ['student_id', 'course_id'])
    op.create_index('idx_mrl_user', 'material_reading_logs', ['user_id'])
    # Expression index for orchestration_jobs input_config course_id
    op.execute("CREATE INDEX idx_orch_jobs_course ON orchestration_jobs (((input_config->'job_context'->>'course_id')::int))")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_orch_jobs_course")
    op.drop_index('idx_mrl_user', table_name='material_reading_logs')
    op.drop_index('idx_sql_student_course', table_name='student_question_logs')
    op.drop_index('idx_sctl_student_course', table_name='student_chatbot_turn_logs')
    op.drop_index('idx_scd_student_course', table_name='student_chatbot_dialogs')
