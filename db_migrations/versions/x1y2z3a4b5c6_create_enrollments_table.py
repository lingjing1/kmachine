"""create enrollments table

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
Create Date: 2026-01-23 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'w0x1y2z3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 建立選課表 (ENROLLMENTS)
    # ============================================================
    op.create_table(
        'enrollments',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('enrolled_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('enrollment_method', sa.String(length=20), server_default='student_code', nullable=False),
        
        # 外鍵
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        
        # 主鍵
        sa.PrimaryKeyConstraint('user_id', 'course_id'),
        
        # 檢查約束
        sa.CheckConstraint("enrollment_method IN ('student_code', 'teacher_add', 'import')", name='ck_enrollment_method')
    )
    
    # 建立索引
    op.create_index('idx_enrollments_course', 'enrollments', ['course_id'], unique=False)
    op.create_index('idx_enrollments_user', 'enrollments', ['user_id'], unique=False)
    op.create_index('idx_enrollments_method', 'enrollments', ['enrollment_method'], unique=False)
    
    # ============================================================
    # 新增課程註冊碼欄位到 COURSES 表
    # ============================================================
    op.add_column('courses', sa.Column('enrollment_code', sa.String(length=10), nullable=True))
    op.add_column('courses', sa.Column('enrollment_code_expires_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_unique_constraint('uq_courses_enrollment_code', 'courses', ['enrollment_code'])
    
    # Add comments
    op.execute("COMMENT ON TABLE enrollments IS '學生選課記錄表'")
    op.execute("COMMENT ON COLUMN courses.enrollment_code IS '課程註冊碼 (6-8位數字)'")
    op.execute("COMMENT ON COLUMN enrollments.user_id IS '學生 ID (FK -> users.id)'")
    op.execute("COMMENT ON COLUMN enrollments.course_id IS '課程 ID (FK -> courses.id)'")
    op.execute("COMMENT ON COLUMN enrollments.enrolled_at IS '選課時間'")
    op.execute("COMMENT ON COLUMN enrollments.enrollment_method IS '選課方式: student_code(學生輸入碼)/teacher_add(教師加入)/import(批次匯入)'")


def downgrade() -> None:
    # 刪除 courses 表新增的欄位
    op.drop_constraint('uq_courses_enrollment_code', 'courses', type_='unique')
    op.drop_column('courses', 'enrollment_code_expires_at')
    op.drop_column('courses', 'enrollment_code')

    # 刪除 enrollments 表
    op.drop_index('idx_enrollments_method', table_name='enrollments')
    op.drop_index('idx_enrollments_user', table_name='enrollments')
    op.drop_index('idx_enrollments_course', table_name='enrollments')
    op.drop_table('enrollments')
