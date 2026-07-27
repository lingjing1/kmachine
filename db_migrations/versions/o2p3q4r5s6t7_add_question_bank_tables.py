"""add question bank tables

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-01-14 17:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'o2p3q4r5s6t7'
down_revision: Union[str, None] = '3000bcb42b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Step 1: 建立 question_bank 表（核心題庫）
    # ============================================================
    op.create_table(
        'question_bank',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('creator_id', sa.Integer(), nullable=False),
        
        # 基本資訊
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # 題目內容（JSONB 格式）
        sa.Column('question_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        
        # 分類屬性
        sa.Column('question_type', sa.String(50), nullable=False),
        sa.Column('difficulty_level', sa.String(20), nullable=True),
        sa.Column('estimated_time_minutes', sa.Integer(), nullable=True),
        
        # 標籤系統（PostgreSQL Array）
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        
        # 統計元數據
        sa.Column('times_used', sa.Integer(), server_default='0', nullable=False),
        sa.Column('average_score', sa.Numeric(5, 2), nullable=True),
        
        # 狀態與審計
        sa.Column('is_published', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "difficulty_level IN ('easy', 'medium', 'hard') OR difficulty_level IS NULL",
            name='valid_difficulty'
        ),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'short_answer', 'true_false', 'fill_in_blank', 'matching')",
            name='valid_question_type'
        )
    )
    
    # Foreign keys for question_bank
    op.create_foreign_key(
        'fk_question_bank_course_id', 'question_bank', 'courses',
        ['course_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_question_bank_creator_id', 'question_bank', 'users',
        ['creator_id'], ['id'], ondelete='SET NULL'
    )
    
    # Indexes for question_bank
    op.create_index('idx_question_bank_course', 'question_bank', ['course_id'])
    op.create_index('idx_question_bank_type', 'question_bank', ['question_type'])
    op.create_index('idx_question_bank_difficulty', 'question_bank', ['difficulty_level'])
    op.create_index('idx_question_bank_tags', 'question_bank', ['tags'], postgresql_using='gin')
    op.create_index(
        'idx_question_bank_published', 'question_bank', ['is_published'],
        postgresql_where=sa.text('is_published = true')
    )
    
    # ============================================================
    # Step 2: 建立 content_questions 關聯表（多對多）
    # ============================================================
    op.create_table(
        'content_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('points', sa.Numeric(5, 2), nullable=True),
        sa.Column('added_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('content_id', 'question_id', name='unique_content_question')
    )
    
    # Foreign keys for content_questions
    op.create_foreign_key(
        'fk_content_questions_content_id', 'content_questions', 'course_contents',
        ['content_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_content_questions_question_id', 'content_questions', 'question_bank',
        ['question_id'], ['id'], ondelete='RESTRICT'
    )
    
    # Indexes for content_questions
    op.create_index('idx_content_questions_content', 'content_questions', ['content_id'])
    op.create_index('idx_content_questions_question', 'content_questions', ['question_id'])
    op.create_index('idx_content_questions_order', 'content_questions', ['content_id', 'display_order'])
    
    # ============================================================
    # Step 3: 建立觸發器函數
    # ============================================================
    
    # 自動更新 updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_question_bank_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW() AT TIME ZONE 'Asia/Taipei';
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trigger_update_question_bank_timestamp
        BEFORE UPDATE ON question_bank
        FOR EACH ROW
        EXECUTE FUNCTION update_question_bank_updated_at();
    """)
    
    # 增加引用計數
    op.execute("""
        CREATE OR REPLACE FUNCTION increment_question_usage()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE question_bank 
            SET times_used = times_used + 1 
            WHERE id = NEW.question_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trigger_increment_usage
        AFTER INSERT ON content_questions
        FOR EACH ROW
        EXECUTE FUNCTION increment_question_usage();
    """)
    
    # 減少引用計數
    op.execute("""
        CREATE OR REPLACE FUNCTION decrement_question_usage()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE question_bank 
            SET times_used = GREATEST(times_used - 1, 0)
            WHERE id = OLD.question_id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trigger_decrement_usage
        AFTER DELETE ON content_questions
        FOR EACH ROW
        EXECUTE FUNCTION decrement_question_usage();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS trigger_update_question_bank_timestamp ON question_bank')
    op.execute('DROP TRIGGER IF EXISTS trigger_increment_usage ON content_questions')
    op.execute('DROP TRIGGER IF EXISTS trigger_decrement_usage ON content_questions')
    
    # Drop functions
    op.execute('DROP FUNCTION IF EXISTS update_question_bank_updated_at()')
    op.execute('DROP FUNCTION IF EXISTS increment_question_usage()')
    op.execute('DROP FUNCTION IF EXISTS decrement_question_usage()')
    
    # Drop tables (順序很重要：先刪除依賴表)
    op.drop_table('content_questions')
    op.drop_table('question_bank')
