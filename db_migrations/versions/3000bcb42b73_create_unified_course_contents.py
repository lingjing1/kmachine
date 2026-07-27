"""create_unified_course_contents

Revision ID: 3000bcb42b73
Revises: n1o2p3q4r5s6
Create Date: 2026-01-10 12:34:02.352637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3000bcb42b73'
down_revision: Union[str, Sequence[str], None] = 'n1o2p3q4r5s6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create course_contents table
    op.create_table(
        'course_contents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content_type', sa.String(50), nullable=False),
        # Source & Content
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('content', postgresql.JSON(astext_type=sa.Text()), nullable=True), # Added content field
        # Grading
        sa.Column('include_in_grade', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('weight', sa.Numeric(5, 2), server_default='0.00', nullable=True),
        sa.Column('total_points', sa.Numeric(6, 2), server_default='100.00', nullable=True),
        sa.Column('question_grading', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        # Time
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        # Assignment specific
        sa.Column('assignment_timing', sa.String(50), nullable=True),
        # Exam specific
        sa.Column('exam_type_category', sa.String(50), nullable=True),
        sa.Column('is_published', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('allow_review', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('show_answers_after', sa.DateTime(), nullable=True),
        # Display
        sa.Column('is_visible', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        # Meta
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indices & FKs for course_contents
    op.create_foreign_key('fk_course_contents_course_id', 'course_contents', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_course_contents_unit_id', 'course_contents', 'course_units', ['unit_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_course_contents_author_id', 'course_contents', 'users', ['author_id'], ['id'], ondelete='CASCADE')
    
    op.create_index('idx_course_contents_course', 'course_contents', ['course_id'])
    op.create_index('idx_course_contents_unit', 'course_contents', ['unit_id'])
    op.create_index('idx_course_contents_type', 'course_contents', ['content_type'])
    op.create_index('idx_course_contents_source', 'course_contents', ['source_type', 'source_id'])

    # 2. Update Submissions tables
    # submissions_assignment
    op.add_column('submissions_assignment', sa.Column('content_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_submissions_assignment_content_id', 'submissions_assignment', 'course_contents', ['content_id'], ['id'], ondelete='CASCADE')
    
    # Drop old link to assignments table
    op.drop_constraint('fk_submissions_assignment_id', 'submissions_assignment', type_='foreignkey')
    op.drop_index('idx_submissions_assignment_id', table_name='submissions_assignment') 
    
    op.drop_column('submissions_assignment', 'assignment_id')
    
    # Use raw SQL to safe drop
    op.execute("ALTER TABLE submissions_assignment DROP CONSTRAINT IF EXISTS uq_submissions_assignment_user")

    op.create_unique_constraint('uq_submissions_assignment_content_user', 'submissions_assignment', ['content_id', 'user_id'])


    # submissions_exam
    op.add_column('submissions_exam', sa.Column('content_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_submissions_exam_content_id', 'submissions_exam', 'course_contents', ['content_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('fk_submissions_exam_exam_id', 'submissions_exam', type_='foreignkey')
    op.drop_index('idx_submissions_exam_exam_id', table_name='submissions_exam')
    op.drop_column('submissions_exam', 'exam_id')
    
    # Use raw SQL to safe drop
    op.execute("ALTER TABLE submissions_exam DROP CONSTRAINT IF EXISTS uq_submissions_exam_exam_user")
    
    op.create_unique_constraint('uq_submissions_exam_content_user', 'submissions_exam', ['content_id', 'user_id'])


    # 3. Drop old tables
    # course_materials
    op.drop_table('course_materials')
    # course_assignments
    op.drop_table('course_assignments')
    # course_exams
    op.drop_table('course_exams')


def downgrade() -> None:
    # 1. Recreate course_materials
    op.create_table(
        'course_materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('course_unit_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('is_visible', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_course_materials_course_id', 'course_materials', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_course_materials_course_unit_id', 'course_materials', 'course_units', ['course_unit_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_course_materials_course_id', 'course_materials', ['course_id'])
    op.create_index('idx_course_materials_course_unit_id', 'course_materials', ['course_unit_id'])

    # 2. Recreate course_assignments
    op.create_table(
        'course_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('course_unit_id', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('assignment_timing', sa.String(50), nullable=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('include_in_grade', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('weight', sa.Numeric(5, 2), server_default='0.00', nullable=False),
        sa.Column('total_points', sa.Numeric(6, 2), server_default='100.00', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_course_assignments_course', 'course_assignments', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_course_assignments_unit', 'course_assignments', 'course_units', ['course_unit_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_course_assignments_author', 'course_assignments', 'users', ['author_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_assignments_course_id', 'course_assignments', ['course_id'])
    op.create_index('idx_assignments_source', 'course_assignments', ['source_type', 'source_id'])

    # 3. Recreate course_exams
    op.create_table(
        'course_exams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('course_unit_id', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('exam_type_category', sa.String(50), nullable=True),
        sa.Column('exam_type_custom', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('include_in_grade', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('weight', sa.Numeric(5, 2), server_default='0.00', nullable=False),
        sa.Column('total_points', sa.Numeric(6, 2), server_default='100.00', nullable=False),
        sa.Column('question_grading', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('is_published', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('allow_review', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('show_answers_after', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_course_exams_course_id', 'course_exams', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_course_exams_course_unit_id', 'course_exams', 'course_units', ['course_unit_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_course_exams_author_id', 'course_exams', 'users', ['author_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_course_exams_course_id', 'course_exams', ['course_id'])
    op.create_index('idx_course_exams_course_unit_id', 'course_exams', ['course_unit_id'])
    op.create_index('idx_course_exams_author_id', 'course_exams', ['author_id'])
    op.create_index('idx_course_exams_source', 'course_exams', ['source_type', 'source_id'])
    op.create_index('idx_course_exams_start_time', 'course_exams', ['start_time'])

    # 4. Revert submissions_assignment
    op.drop_constraint('uq_submissions_assignment_content_user', 'submissions_assignment', type_='unique')
    op.drop_constraint('fk_submissions_assignment_content_id', 'submissions_assignment', type_='foreignkey')
    op.drop_column('submissions_assignment', 'content_id')
    op.add_column('submissions_assignment', sa.Column('assignment_id', sa.Integer(), nullable=False))
    
    op.create_foreign_key('fk_submissions_assignment_id', 'submissions_assignment', 'course_assignments', ['assignment_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_submissions_assignment_id', 'submissions_assignment', ['assignment_id'])
    # op.create_unique_constraint('uq_submissions_assignment_user', 'submissions_assignment', ['assignment_id', 'user_id'])
    

    # 5. Revert submissions_exam
    op.drop_constraint('uq_submissions_exam_content_user', 'submissions_exam', type_='unique')
    op.drop_constraint('fk_submissions_exam_content_id', 'submissions_exam', type_='foreignkey')
    op.drop_column('submissions_exam', 'content_id')
    op.add_column('submissions_exam', sa.Column('exam_id', sa.Integer(), nullable=False))
    op.create_foreign_key('fk_submissions_exam_exam_id', 'submissions_exam', 'course_exams', ['exam_id'], ['id'], ondelete='CASCADE')
    op.create_index('idx_submissions_exam_exam_id', 'submissions_exam', ['exam_id'])
    op.create_unique_constraint('uq_submissions_exam_exam_user', 'submissions_exam', ['exam_id', 'user_id'])

    # 6. Drop course_contents
    op.drop_table('course_contents')
