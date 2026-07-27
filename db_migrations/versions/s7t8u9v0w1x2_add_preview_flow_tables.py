"""add preview flow tables

Revision ID: s7t8u9v0w1x2
Revises: r5s6t7u8v9w0
Create Date: 2026-01-18 22:28:00.000000

簡化版：只建立 2 張表
1. knowledge_point_contents - Preview/Review 教材內容
2. student_question_logs - 學生作答記錄（支援課後推薦錯題）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 's7t8u9v0w1x2'
down_revision: Union[str, None] = 'p3q4r5s6t7u9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Part 1: 調整 question_bank 表 - 加入 unit_id 和 kp_id
    # ============================================================
    
    op.add_column('question_bank', sa.Column('unit_id', sa.Integer(), nullable=True))
    op.add_column('question_bank', sa.Column('kp_id', sa.Integer(), nullable=True))
    
    # 建立外鍵約束
    op.create_foreign_key(
        'fk_question_bank_unit_id', 
        'question_bank', 
        'course_units',
        ['unit_id'], 
        ['id'], 
        ondelete='SET NULL'
    )
    
    op.create_foreign_key(
        'fk_question_bank_kp_id', 
        'question_bank', 
        'knowledge_points',
        ['kp_id'], 
        ['id'], 
        ondelete='SET NULL'
    )
    
    # 建立索引
    op.create_index('idx_question_bank_unit', 'question_bank', ['unit_id'])
    op.create_index('idx_question_bank_kp', 'question_bank', ['kp_id'])
    
    # ============================================================
    # Part 2: 建立 knowledge_point_contents 表
    # ============================================================
    
    op.create_table(
        'knowledge_point_contents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(20), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=False),
        sa.Column('content_plain', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('knowledge_point_id', 'content_type', name='uq_kp_content_type'),
        sa.CheckConstraint(
            "content_type IN ('preview', 'review')",
            name='valid_content_type'
        )
    )
    
    # 外鍵
    op.create_foreign_key(
        'fk_kp_content_kp',
        'knowledge_point_contents',
        'knowledge_points',
        ['knowledge_point_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_kp_content_unit',
        'knowledge_point_contents',
        'course_units',
        ['unit_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    op.create_foreign_key(
        'fk_kp_content_course',
        'knowledge_point_contents',
        'courses',
        ['course_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # 索引
    op.create_index('idx_kp_contents_kp', 'knowledge_point_contents', ['knowledge_point_id'])
    op.create_index('idx_kp_contents_unit', 'knowledge_point_contents', ['unit_id'])
    op.create_index('idx_kp_contents_course', 'knowledge_point_contents', ['course_id'])
    op.create_index('idx_kp_contents_type', 'knowledge_point_contents', ['content_type'])
    
    # ============================================================
    # Part 3: 建立 student_question_logs 表（簡化版）
    # ============================================================
    
    op.create_table(
        'student_question_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        
        sa.Column('stage', sa.String(20), nullable=False),  # 'preview' 或 'review'
        
        # 答案與評價
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('correctness', sa.String(20), nullable=True),  # 'correct', 'partially_correct', 'incorrect'
        sa.Column('feedback', sa.Text(), nullable=True),
        
        # 時間記錄
        sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "stage IN ('preview', 'review')",
            name='valid_stage'
        ),
        sa.CheckConstraint(
            "correctness IN ('correct', 'partially_correct', 'incorrect') OR correctness IS NULL",
            name='valid_correctness'
        )
    )
    
    # 外鍵
    op.create_foreign_key('fk_sql_student', 'student_question_logs', 'users', ['student_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_sql_question', 'student_question_logs', 'question_bank', ['question_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_sql_kp', 'student_question_logs', 'knowledge_points', ['knowledge_point_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_sql_unit', 'student_question_logs', 'course_units', ['unit_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_sql_course', 'student_question_logs', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    
    # 索引
    op.create_index('idx_sql_student', 'student_question_logs', ['student_id'])
    op.create_index('idx_sql_kp_stage', 'student_question_logs', ['knowledge_point_id', 'stage'])
    op.create_index('idx_sql_student_kp', 'student_question_logs', ['student_id', 'knowledge_point_id'])
    op.create_index('idx_sql_correctness', 'student_question_logs', ['correctness'])


def downgrade() -> None:
    # Part 3: 刪除 student_question_logs
    op.drop_index('idx_sql_correctness', table_name='student_question_logs')
    op.drop_index('idx_sql_student_kp', table_name='student_question_logs')
    op.drop_index('idx_sql_kp_stage', table_name='student_question_logs')
    op.drop_index('idx_sql_student', table_name='student_question_logs')
    op.drop_table('student_question_logs')
    
    # Part 2: 刪除 knowledge_point_contents
    op.drop_index('idx_kp_contents_type', table_name='knowledge_point_contents')
    op.drop_index('idx_kp_contents_course', table_name='knowledge_point_contents')
    op.drop_index('idx_kp_contents_unit', table_name='knowledge_point_contents')
    op.drop_index('idx_kp_contents_kp', table_name='knowledge_point_contents')
    op.drop_table('knowledge_point_contents')
    
    # Part 1: 移除 question_bank 的新欄位
    op.drop_index('idx_question_bank_kp', table_name='question_bank')
    op.drop_index('idx_question_bank_unit', table_name='question_bank')
    op.drop_constraint('fk_question_bank_kp_id', 'question_bank', type_='foreignkey')
    op.drop_constraint('fk_question_bank_unit_id', 'question_bank', type_='foreignkey')
    op.drop_column('question_bank', 'kp_id')
    op.drop_column('question_bank', 'unit_id')
