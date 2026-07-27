"""cleanup_submissions_assignment

Revision ID: 2e708246ce23
Revises: 5749796ffb90
Create Date: 2026-03-10 14:21:27.693927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e708246ce23'
down_revision: Union[str, Sequence[str], None] = '5749796ffb90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add percentage column
    op.add_column('submissions_assignment', sa.Column('percentage', sa.Float(), nullable=True))
    
    # Drop redundant file columns
    op.drop_column('submissions_assignment', 'file_name')
    op.drop_column('submissions_assignment', 'original_file_name')
    op.drop_column('submissions_assignment', 'file_path')
    op.drop_column('submissions_assignment', 'file_size_bytes')
    op.drop_column('submissions_assignment', 'file_type')


def downgrade() -> None:
    """Downgrade schema."""
    # Add back file columns
    op.add_column('submissions_assignment', sa.Column('file_type', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    op.add_column('submissions_assignment', sa.Column('file_size_bytes', sa.BIGINT(), autoincrement=False, nullable=True))
    op.add_column('submissions_assignment', sa.Column('file_path', sa.VARCHAR(length=1000), autoincrement=False, nullable=True))
    op.add_column('submissions_assignment', sa.Column('original_file_name', sa.VARCHAR(length=500), autoincrement=False, nullable=True))
    op.add_column('submissions_assignment', sa.Column('file_name', sa.VARCHAR(length=500), autoincrement=False, nullable=True))
    
    # Drop percentage column
    op.drop_column('submissions_assignment', 'percentage')
