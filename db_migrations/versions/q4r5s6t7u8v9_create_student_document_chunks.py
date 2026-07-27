"""create_student_document_chunks

Revision ID: q4r5s6t7u8v9
Revises: b98d69e1bc31
Create Date: 2026-01-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'q4r5s6t7u8v9'
down_revision: Union[str, Sequence[str], None] = 'b98d69e1bc31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create student_document_chunks table
    op.create_table(
        'student_document_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=True),
        sa.Column('source_filename', sa.String(255), nullable=True),
        sa.Column('chunk_order', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('page_numbers', sa.String(100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes
    op.create_index('idx_student_doc_chunks_course', 'student_document_chunks', ['course_id'])
    op.create_index('idx_student_doc_chunks_unit', 'student_document_chunks', ['unit_id'])
    op.create_index('idx_student_doc_chunks_kp', 'student_document_chunks', ['knowledge_point_id'])
    
    # Add vector index
    op.execute("""
        CREATE INDEX hnsw_idx_student_doc_chunks_embedding 
        ON student_document_chunks 
        USING HNSW (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.drop_table('student_document_chunks')
