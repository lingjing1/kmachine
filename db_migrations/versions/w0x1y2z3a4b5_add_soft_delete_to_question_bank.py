"""add soft delete to question bank

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2026-01-21 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'w0x1y2z3a4b5'
down_revision: Union[str, Sequence[str], None] = 'v9w0x1y2z3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add soft delete fields and times_used trigger to question_bank."""
    
    # ============================================================
    # Step 1: 添加軟刪除欄位
    # ============================================================
    op.add_column('question_bank', 
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('question_bank', 
        sa.Column('deleted_at', sa.DateTime(), nullable=True))
    
    # 添加索引以加速查詢 (只索引未刪除的)
    op.create_index(
        'idx_question_bank_active', 
        'question_bank', 
        ['course_id', 'is_deleted'],
        postgresql_where=sa.text('is_deleted = false')
    )
    
    # ============================================================
    # Step 2: 創建觸發器維護 times_used (基於 course_contents JSONB)
    # ============================================================
    
    # 此觸發器會掃描 course_contents.content JSONB 中的 saved_question_bank_id
    # 並自動更新 question_bank.times_used
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_question_bank_usage()
        RETURNS TRIGGER AS $$
        DECLARE
            new_ids INTEGER[];
            old_ids INTEGER[];
            id_to_process INTEGER;
        BEGIN
            -- 提取新內容中的所有 saved_question_bank_id
            IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
                SELECT ARRAY_AGG(DISTINCT (elem->>'saved_question_bank_id')::int)
                INTO new_ids
                FROM jsonb_array_elements(
                    CASE 
                        WHEN jsonb_typeof(NEW.content) = 'object' 
                        THEN COALESCE(NEW.content->'content', '[]'::jsonb)
                        ELSE NEW.content
                    END
                ) AS elem
                WHERE elem->>'saved_question_bank_id' IS NOT NULL
                  AND elem->>'saved_question_bank_id' != 'null'
                  AND elem->>'saved_question_bank_id' ~ '^[0-9]+$';
            END IF;
            
            -- 提取舊內容中的 saved_question_bank_id (UPDATE/DELETE)
            IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
                SELECT ARRAY_AGG(DISTINCT (elem->>'saved_question_bank_id')::int)
                INTO old_ids
                FROM jsonb_array_elements(
                    CASE 
                        WHEN jsonb_typeof(OLD.content) = 'object' 
                        THEN COALESCE(OLD.content->'content', '[]'::jsonb)
                        ELSE OLD.content
                    END
                ) AS elem
                WHERE elem->>'saved_question_bank_id' IS NOT NULL
                  AND elem->>'saved_question_bank_id' != 'null'
                  AND elem->>'saved_question_bank_id' ~ '^[0-9]+$';
            END IF;
            
            -- 增加計數：在 new_ids 中但不在 old_ids 中的 ID
            IF new_ids IS NOT NULL THEN
                FOREACH id_to_process IN ARRAY new_ids
                LOOP
                    IF old_ids IS NULL OR id_to_process != ALL(old_ids) THEN
                        UPDATE question_bank
                        SET times_used = times_used + 1
                        WHERE id = id_to_process;
                    END IF;
                END LOOP;
            END IF;
            
            -- 減少計數：在 old_ids 中但不在 new_ids 中的 ID
            IF old_ids IS NOT NULL THEN
                FOREACH id_to_process IN ARRAY old_ids
                LOOP
                    IF new_ids IS NULL OR id_to_process != ALL(new_ids) THEN
                        UPDATE question_bank
                        SET times_used = GREATEST(times_used - 1, 0)
                        WHERE id = id_to_process;
                    END IF;
                END LOOP;
            END IF;
            
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # 綁定觸發器到 course_contents
    op.execute("""
        CREATE TRIGGER trg_sync_question_bank_usage
        AFTER INSERT OR UPDATE OR DELETE ON course_contents
        FOR EACH ROW
        EXECUTE FUNCTION sync_question_bank_usage();
    """)


def downgrade() -> None:
    """Remove soft delete fields and times_used trigger."""
    
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_sync_question_bank_usage ON course_contents")
    op.execute("DROP FUNCTION IF EXISTS sync_question_bank_usage()")
    
    # Drop index and columns
    op.drop_index('idx_question_bank_active', table_name='question_bank')
    op.drop_column('question_bank', 'deleted_at')
    op.drop_column('question_bank', 'is_deleted')
