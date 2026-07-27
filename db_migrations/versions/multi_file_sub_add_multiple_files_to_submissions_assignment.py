"""add_multiple_files_to_submissions_assignment

Revision ID: multi_file_sub
Revises: 8bb785c8b4fe
Create Date: 2026-03-03 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'multi_file_sub'
down_revision: Union[str, Sequence[str], None] = '8bb785c8b4fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add files JSONB column
    op.add_column('submissions_assignment', sa.Column(
        'files', 
        postgresql.JSONB(astext_type=sa.Text()), 
        nullable=True,
        server_default='[]',
        comment="List of uploaded files for this submission. format: [{name, original_name, path, size, type, uploaded_at}]"
    ))

    # 2. Migrate existing single file data to the new JSONB column
    # We create a JSON object for the existing file columns and put it into an array
    op.execute("""
        UPDATE submissions_assignment
        SET files = jsonb_build_array(
            jsonb_build_object(
                'name', file_name,
                'original_name', original_file_name,
                'path', file_path,
                'size', file_size_bytes,
                'type', file_type,
                'uploaded_at', COALESCE(updated_at, submitted_at)
            )
        )
        WHERE file_path IS NOT NULL
    """)


def downgrade() -> None:
    # 1. Move back the first file from JSONB to flat columns (Best effort)
    op.execute("""
        UPDATE submissions_assignment
        SET file_name = files->0->>'name',
            original_file_name = files->0->>'original_name',
            file_path = files->0->>'path',
            file_size_bytes = (files->0->>'size')::bigint,
            file_type = files->0->>'type'
        WHERE files IS NOT NULL AND jsonb_array_length(files) > 0
    """)

    # 2. Drop the column
    op.drop_column('submissions_assignment', 'files')
