"""add grading system tables and fields

Revision ID: n1o2p3q4r5s6
Revises: m8n9o0p1q2r3
Create Date: 2026-01-09 13:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, None] = 'm8n9o0p1q2r3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================
    # 1. 為 course_assignments 添加配分欄位
    # ========================================
    op.add_column('course_assignments',
        sa.Column('include_in_grade', sa.Boolean(), server_default='true', nullable=False)
    )
    op.add_column('course_assignments',
        sa.Column('weight', sa.Numeric(5, 2), server_default='0.00', nullable=False)
    )
    op.add_column('course_assignments',
        sa.Column('total_points', sa.Numeric(6, 2), server_default='100.00', nullable=False)
    )
    
    # ========================================
    # 2. 重新命名 submissions → submissions_assignment
    # ========================================
    op.rename_table('submissions', 'submissions_assignment')
    
    # ========================================
    # 3. 創建 course_exams 表格
    # ========================================
    op.create_table(
        'course_exams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('course_unit_id', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # 考試類型設定 (支援自訂)
        sa.Column('exam_type_category', sa.String(50), nullable=True),
        sa.Column('exam_type_custom', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        
        # 課程層級配分
        sa.Column('include_in_grade', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('weight', sa.Numeric(5, 2), server_default='0.00', nullable=False),
        sa.Column('total_points', sa.Numeric(6, 2), server_default='100.00', nullable=False),
        
        # 考卷層級配分 (題目配分)
        sa.Column('question_grading', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        
        # 多型關聯到內容來源
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        
        # 考試設定
        sa.Column('is_published', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('allow_review', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('show_answers_after', sa.DateTime(), nullable=True),
        
        # 時間戳記
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # course_exams Foreign keys
    op.create_foreign_key(
        'fk_course_exams_course_id', 'course_exams', 'courses',
        ['course_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_course_exams_course_unit_id', 'course_exams', 'course_units',
        ['course_unit_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_course_exams_author_id', 'course_exams', 'users',
        ['author_id'], ['id'], ondelete='CASCADE'
    )
    
    # course_exams Indexes
    op.create_index('idx_course_exams_course_id', 'course_exams', ['course_id'])
    op.create_index('idx_course_exams_course_unit_id', 'course_exams', ['course_unit_id'])
    op.create_index('idx_course_exams_author_id', 'course_exams', ['author_id'])
    op.create_index('idx_course_exams_source', 'course_exams', ['source_type', 'source_id'])
    op.create_index('idx_course_exams_start_time', 'course_exams', ['start_time'])
    
    # ========================================
    # 4. 創建 submissions_exam 表格
    # ========================================
    op.create_table(
        'submissions_exam',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exam_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        
        # 作答內容
        sa.Column('content', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        
        # 成績
        sa.Column('score', sa.Numeric(6, 2), nullable=True),
        sa.Column('percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('grade', sa.String(10), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        
        # 作答時間記錄
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('time_spent_minutes', sa.Integer(), nullable=True),
        
        # 狀態
        sa.Column('status', sa.String(50), server_default='submitted', nullable=False),
        sa.Column('is_late', sa.Boolean(), server_default='false', nullable=False),
        
        # 時間戳記
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'user_id', name='uq_submissions_exam_exam_user')
    )
    
    # submissions_exam Foreign keys
    op.create_foreign_key(
        'fk_submissions_exam_exam_id', 'submissions_exam', 'course_exams',
        ['exam_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_submissions_exam_user_id', 'submissions_exam', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )
    
    # submissions_exam Indexes
    op.create_index('idx_submissions_exam_exam_id', 'submissions_exam', ['exam_id'])
    op.create_index('idx_submissions_exam_user_id', 'submissions_exam', ['user_id'])
    op.create_index('idx_submissions_exam_status', 'submissions_exam', ['status'])
    
    # ========================================
    # 5. 創建 course_grades 總成績表
    # ========================================
    op.create_table(
        'course_grades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        
        # 總成績計算
        sa.Column('total_score', sa.Numeric(6, 2), nullable=True),
        sa.Column('percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('letter_grade', sa.String(10), nullable=True),
        
        sa.Column('grade_breakdown', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        
        # 統計資訊
        sa.Column('assignments_completed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('assignments_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('exams_completed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('exams_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('participation_score', sa.Numeric(5, 2), server_default='0.00', nullable=False),
        
        # 教師覆寫功能
        sa.Column('teacher_override_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('teacher_override_score', sa.Numeric(6, 2), nullable=True),
        sa.Column('teacher_override_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('teacher_override_letter_grade', sa.String(10), nullable=True),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('overridden_by', sa.Integer(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(), nullable=True),
        
        # 學生可見性控制
        sa.Column('is_visible_to_student', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('visible_from', sa.DateTime(), nullable=True),
        
        # 成績狀態管理
        sa.Column('grade_status', sa.String(50), server_default='draft', nullable=False),
        
        # 排名與統計
        sa.Column('class_rank', sa.Integer(), nullable=True),
        sa.Column('class_percentile', sa.Numeric(5, 2), nullable=True),
        sa.Column('class_average', sa.Numeric(6, 2), nullable=True),
        
        # 審核追蹤
        sa.Column('last_calculated_at', sa.DateTime(), nullable=True),
        sa.Column('last_modified_by', sa.Integer(), nullable=True),
        
        # 狀態
        sa.Column('is_finalized', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('finalized_at', sa.DateTime(), nullable=True),
        sa.Column('finalized_by', sa.Integer(), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        
        # 時間戳記
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id', 'user_id', name='uq_course_grades_course_user')
    )
    
    # course_grades Foreign keys
    op.create_foreign_key(
        'fk_course_grades_course_id', 'course_grades', 'courses',
        ['course_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_course_grades_user_id', 'course_grades', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_course_grades_overridden_by', 'course_grades', 'users',
        ['overridden_by'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_course_grades_last_modified_by', 'course_grades', 'users',
        ['last_modified_by'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_course_grades_finalized_by', 'course_grades', 'users',
        ['finalized_by'], ['id'], ondelete='SET NULL'
    )
    
    # course_grades Indexes
    op.create_index('idx_course_grades_course_id', 'course_grades', ['course_id'])
    op.create_index('idx_course_grades_user_id', 'course_grades', ['user_id'])
    op.create_index('idx_course_grades_status', 'course_grades', ['grade_status'])
    op.create_index('idx_course_grades_visible', 'course_grades', ['is_visible_to_student'])


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table('course_grades')
    op.drop_table('submissions_exam')
    op.drop_table('course_exams')
    
    # Rename back
    op.rename_table('submissions_assignment', 'submissions')
    
    # Remove columns from course_assignments
    op.drop_column('course_assignments', 'total_points')
    op.drop_column('course_assignments', 'weight')
    op.drop_column('course_assignments', 'include_in_grade')
