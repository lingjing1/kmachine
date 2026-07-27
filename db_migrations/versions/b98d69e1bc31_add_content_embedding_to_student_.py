"""add_content_embedding_to_student_chatbot_dialogs

Revision ID: b98d69e1bc31
Revises: p3q4r5s6t7u8
Create Date: 2026-01-14 21:57:59.451226

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b98d69e1bc31'
down_revision: Union[str, Sequence[str], None] = 'p3q4r5s6t7u8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 content_embedding 欄位
    op.execute("""
    ALTER TABLE student_chatbot_dialogs 
    ADD COLUMN content_embedding VECTOR(1536);
    """)

    # 2. 建立 HNSW 向量索引
    op.execute("""
    CREATE INDEX hnsw_idx_dialog_embedding
    ON student_chatbot_dialogs
    USING HNSW (content_embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    # 1. 刪除索引
    op.execute("DROP INDEX IF EXISTS hnsw_idx_dialog_embedding;")

    # 2. 刪除欄位
    op.execute("""
    ALTER TABLE student_chatbot_dialogs 
    DROP COLUMN content_embedding;
    """)
