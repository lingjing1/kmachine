"""create student_chatbot_turn_logs table

Revision ID: 20260304_turn_logs
Revises: multi_file_sub
Create Date: 2026-03-04 21:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY


# Alembic 版本識別碼
revision: str = '20260304_turn_logs'
down_revision: Union[str, Sequence[str], None] = 'multi_file_sub'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    新增 student_chatbot_turn_logs 表。
    每個學生提問回合（user 問一次 + AI 答一次）記錄一筆完整記錄，
    用於成本分析與對話研究。
    """
    op.create_table(
        'student_chatbot_turn_logs',

        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),

        # 關聯
        sa.Column('conversation_id', sa.Text, nullable=False),
        sa.Column('student_id', sa.Integer, nullable=False),
        sa.Column('course_id', sa.Integer, nullable=False),
        sa.Column('unit_id', sa.Integer, nullable=True),
        sa.Column('user_message_id', sa.Integer, nullable=True),
        sa.Column('ai_message_id', sa.Integer, nullable=True),

        # 輸入/輸出（研究用）
        sa.Column('user_query', sa.Text, nullable=False),
        sa.Column('full_prompt', sa.Text, nullable=True),
        sa.Column('ai_response', sa.Text, nullable=True),
        sa.Column('scaffolding_strategy', sa.Text, nullable=True),

        # 精熟度快照
        sa.Column('mastery_snapshot', JSONB, nullable=True),
        sa.Column('weak_points', ARRAY(sa.Text), nullable=True),

        # RAG 資訊
        sa.Column('rag_candidates_count', sa.Integer, server_default='0'),
        sa.Column('rag_top_results', JSONB, nullable=True),
        sa.Column('rag_cited_chunk_ids', ARRAY(sa.Integer), nullable=True),

        # 成本明細（拆開 embedding vs LLM）
        sa.Column('embedding_tokens', sa.Integer, server_default='0'),
        sa.Column('llm_prompt_tokens', sa.Integer, server_default='0'),
        sa.Column('llm_completion_tokens', sa.Integer, server_default='0'),
        sa.Column('embedding_cost_usd', sa.Numeric(10, 6), server_default='0'),
        sa.Column('llm_cost_usd', sa.Numeric(10, 6), server_default='0'),
        sa.Column('total_cost_usd', sa.Numeric(10, 6), server_default='0'),

        # 延遲明細（各 Agent 各自計時，單位 ms）
        sa.Column('dialog_agent_ms', sa.Integer, nullable=True),
        sa.Column('mastery_agent_ms', sa.Integer, nullable=True),
        sa.Column('retrieval_agent_ms', sa.Integer, nullable=True),
        sa.Column('scaffolding_agent_ms', sa.Integer, nullable=True),
        sa.Column('total_latency_ms', sa.Integer, nullable=True),

        # 上下文統計
        sa.Column('dialog_history_length', sa.Integer, nullable=True),
        sa.Column('related_dialogs_count', sa.Integer, nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # 研究查詢常用的 index
    op.create_index('idx_turn_logs_student_course', 'student_chatbot_turn_logs', ['student_id', 'course_id'])
    op.create_index('idx_turn_logs_conversation', 'student_chatbot_turn_logs', ['conversation_id'])
    op.create_index('idx_turn_logs_created_at', 'student_chatbot_turn_logs', ['created_at'])


def downgrade() -> None:
    """移除 student_chatbot_turn_logs 表和相關索引。"""
    op.drop_index('idx_turn_logs_created_at', table_name='student_chatbot_turn_logs')
    op.drop_index('idx_turn_logs_conversation', table_name='student_chatbot_turn_logs')
    op.drop_index('idx_turn_logs_student_course', table_name='student_chatbot_turn_logs')
    op.drop_table('student_chatbot_turn_logs')
