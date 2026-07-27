"""add_student_knowledge_mastery_history_table

Revision ID: 41d70c7fe46e
Revises: ec93398d1665
Create Date: 2026-02-24 15:54:17.818945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '41d70c7fe46e'
down_revision: Union[str, Sequence[str], None] = 'ec93398d1665'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'student_knowledge_mastery_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(20), nullable=False),           # 'preview' / 'review'
        sa.Column('mastery_level', sa.String(20), nullable=False),   # '待加強' / '尚可' / '精熟'
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('lime_report_path', sa.String(500), nullable=True),     # 帶時間戳的歷史版本路徑
        sa.Column('lime_report_json', postgresql.JSONB(), nullable=True),  # LIME 報告 JSON
        sa.Column('correct_stats', postgresql.JSONB(), nullable=True),     # {"correct":2,"incorrect":1,...}
        sa.Column('assessed_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(
        'idx_mastery_hist_student_kp',
        'student_knowledge_mastery_history',
        ['student_id', 'knowledge_point_id']
    )
    op.create_index(
        'idx_mastery_hist_assessed',
        'student_knowledge_mastery_history',
        ['assessed_at']
    )
    op.create_index(
        'idx_mastery_hist_stage',
        'student_knowledge_mastery_history',
        ['student_id', 'knowledge_point_id', 'stage']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_mastery_hist_stage', table_name='student_knowledge_mastery_history')
    op.drop_index('idx_mastery_hist_assessed', table_name='student_knowledge_mastery_history')
    op.drop_index('idx_mastery_hist_student_kp', table_name='student_knowledge_mastery_history')
    op.drop_table('student_knowledge_mastery_history')
