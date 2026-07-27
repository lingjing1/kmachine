"""add author_id to generated_contents

Revision ID: a7b8c9d0e1f2
Revises: z4a5b6c7d8e9
Create Date: 2026-02-06 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'z4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add author_id column (nullable first to allow existing records)
    op.add_column('generated_contents', sa.Column('author_id', sa.Integer(), nullable=True))
    
    # 2. Add foreign key to users table
    op.create_foreign_key(
        'fk_generated_contents_author_id',
        'generated_contents',
        'users',
        ['author_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Optional: Backfill author_id from linked tasks -> jobs -> users
    # This is a bit complex in pure SQL with the current schema constraints, 
    # but we can try a best-effort update if needed.
    # For now, we leave it nullable and assume new records will have it.


def downgrade() -> None:
    op.drop_constraint('fk_generated_contents_author_id', 'generated_contents', type_='foreignkey')
    op.drop_column('generated_contents', 'author_id')
