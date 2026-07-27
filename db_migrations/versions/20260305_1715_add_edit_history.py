"""20260305_1715_add_edit_history

Revision ID: 20260305_1715_add_edit_history
Revises: 6356bf4757b5
Create Date: 2026-03-05 17:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260305_1715_add_edit_history'
down_revision: Union[str, Sequence[str], None] = '6356bf4757b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add metrics to generated_contents (first save recording)
    op.add_column('generated_contents', sa.Column('levenshtein_distance', sa.Integer(), nullable=True))
    op.add_column('generated_contents', sa.Column('edit_ratio', sa.Float(), nullable=True))
    
    # 2. Add edit_history to course_contents
    op.add_column('course_contents', sa.Column('edit_history', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # 3. Drop redundant metrics from course_contents (clean up)
    op.drop_column('course_contents', 'edit_ratio')
    op.drop_column('course_contents', 'levenshtein_distance')

def downgrade() -> None:
    op.add_column('course_contents', sa.Column('levenshtein_distance', sa.Integer(), nullable=True))
    op.add_column('course_contents', sa.Column('edit_ratio', sa.Float(), nullable=True))
    op.drop_column('course_contents', 'edit_history')
    op.drop_column('generated_contents', 'edit_ratio')
    op.drop_column('generated_contents', 'levenshtein_distance')
