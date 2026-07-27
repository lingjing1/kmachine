"""add_rag_indices

Revision ID: 2c8b494181dc
Revises: z3a4b5c6d7e9
Create Date: 2026-02-05 19:21:01.862270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c8b494181dc'
down_revision: Union[str, Sequence[str], None] = 'z3a4b5c6d7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. document_chunks on unique_content_id
    # 用於 RAG 檢索時，根據 unique_content_id 快速篩選 chunks
    op.create_index(
        'idx_document_chunks_unique_content_id',
        'document_chunks',
        ['unique_content_id'],
        unique=False
    )
    
    # 2. document_content on unique_content_id
    # 用於 RAG 檢索後，根據 unique_content_id 快速回查原始頁面內容 (structured_content)
    op.create_index(
        'idx_document_content_unique_content_id',
        'document_content',
        ['unique_content_id'],
        unique=False
    )
    
    # 3. uploaded_contents on course_id
    # 用於 RAG 前置過濾，根據 course_id 快速查找該課程所有的 unique_content_id
    # 注意：此表已經存在，且可能已有部分索引，但為了保險起見明確建立
    op.create_index(
        'idx_uploaded_contents_course_id',
        'uploaded_contents',
        ['course_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_uploaded_contents_course_id', table_name='uploaded_contents')
    op.drop_index('idx_document_content_unique_content_id', table_name='document_content')
    op.drop_index('idx_document_chunks_unique_content_id', table_name='document_chunks')
