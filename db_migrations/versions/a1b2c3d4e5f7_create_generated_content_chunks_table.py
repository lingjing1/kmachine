"""create_generated_content_chunks_table

Revision ID: a1b2c3d4e5f7
Revises: z3a4b5c6d7e8
Create Date: 2026-02-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = ('z3a4b5c6d7e8', '44b17fe7b7e1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use raw SQL to create table to ensure vector type is handled correctly without alembic type issues
    op.execute("""
    CREATE TABLE generated_content_chunks (
        id SERIAL PRIMARY KEY,
        course_content_id INTEGER NOT NULL,
        chunk_text TEXT,
        chunk_order INTEGER,
        metadata JSONB,
        embedding VECTOR(1536), 
        
        CONSTRAINT fk_gcc_course_content
            FOREIGN KEY(course_content_id) 
            REFERENCES course_contents(id)
            ON DELETE CASCADE
    );
    """)

    # Create HNSW index for fast similarity search
    op.execute("""
    CREATE INDEX IF NOT EXISTS hnsw_idx_generated_content_chunks_embedding
    ON generated_content_chunks
    USING HNSW (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS hnsw_idx_generated_content_chunks_embedding;")
    op.execute("DROP TABLE generated_content_chunks;")
