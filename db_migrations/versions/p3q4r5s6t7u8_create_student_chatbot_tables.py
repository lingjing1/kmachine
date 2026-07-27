"""create_student_chatbot_tables

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-01-14 19:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'p3q4r5s6t7u8'
down_revision: Union[str, Sequence[str], None] = 'o2p3q4r5s6t7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create student_chatbot_dialogs table
    op.create_table(
        'student_chatbot_dialogs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.String(50), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content',postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add foreign keys for student_chatbot_dialogs
    op.create_foreign_key(
        'fk_chatbot_dialog_student',
        'student_chatbot_dialogs', 'users',
        ['student_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_chatbot_dialog_course',
        'student_chatbot_dialogs', 'courses',
        ['course_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_chatbot_dialog_unit',
        'student_chatbot_dialogs', 'course_units',
        ['unit_id'], ['id'],
        ondelete='SET NULL'
    )
    
    op.create_foreign_key(
        'fk_chatbot_dialog_kp',
        'student_chatbot_dialogs', 'knowledge_points',
        ['knowledge_point_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Add indexes for student_chatbot_dialogs
    op.create_index('idx_chatbot_dialog_student', 'student_chatbot_dialogs', ['student_id'])
    op.create_index('idx_chatbot_dialog_course', 'student_chatbot_dialogs', ['course_id'])
    op.create_index('idx_chatbot_dialog_unit', 'student_chatbot_dialogs', ['unit_id'])
    op.create_index('idx_chatbot_dialog_kp', 'student_chatbot_dialogs', ['knowledge_point_id'])
    op.create_index('idx_chatbot_dialog_conversation', 'student_chatbot_dialogs', ['conversation_id'])
    op.create_index('idx_chatbot_dialog_created_at', 'student_chatbot_dialogs', ['created_at'])
    
    # Create student_knowledge_mastery table
    op.create_table(
        'student_knowledge_mastery',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('mastery_level', sa.String(20), nullable=False),
        sa.Column('preview_completed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('review_completed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_assessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'knowledge_point_id', name='uq_student_kp_mastery')
    )
    
    # Add foreign keys for student_knowledge_mastery
    op.create_foreign_key(
        'fk_mastery_student',
        'student_knowledge_mastery', 'users',
        ['student_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_mastery_course',
        'student_knowledge_mastery', 'courses',
        ['course_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_mastery_unit',
        'student_knowledge_mastery', 'course_units',
        ['unit_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_mastery_kp',
        'student_knowledge_mastery', 'knowledge_points',
        ['knowledge_point_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Add indexes for student_knowledge_mastery
    op.create_index('idx_mastery_student', 'student_knowledge_mastery', ['student_id'])
    op.create_index('idx_mastery_course', 'student_knowledge_mastery', ['course_id'])
    op.create_index('idx_mastery_unit', 'student_knowledge_mastery', ['unit_id'])
    op.create_index('idx_mastery_kp', 'student_knowledge_mastery', ['knowledge_point_id'])
    op.create_index('idx_mastery_level', 'student_knowledge_mastery', ['mastery_level'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('student_knowledge_mastery')
    op.drop_table('student_chatbot_dialogs')
