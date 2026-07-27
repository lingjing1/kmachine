"""remove unused cols and unify time

Revision ID: b8c9d0e1f2g3
Revises: a7b8c9d0e1f2
Create Date: 2026-02-07 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2g3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Data Migration: Copy due_date to end_time for homeworks where end_time is null
    # We use raw SQL for this data update
    op.execute("""
        UPDATE course_contents 
        SET end_time = due_date 
        WHERE (content_subtype = 'homework' OR content_type = 'assignment') 
          AND end_time IS NULL 
          AND due_date IS NOT NULL
    """)

    # 2. Drop unused columns
    op.drop_column('course_contents', 'exam_type_category')
    op.drop_column('course_contents', 'assignment_timing')
    op.drop_column('course_contents', 'due_date')


def downgrade() -> None:
    # 1. Add columns back
    op.add_column('course_contents', sa.Column('exam_type_category', sa.String(length=50), nullable=True))
    op.add_column('course_contents', sa.Column('assignment_timing', sa.String(length=50), nullable=True))
    op.add_column('course_contents', sa.Column('due_date', sa.DateTime(), nullable=True))

    # 2. Reverse Data Migration (Optional/Best Effort)
    # We can copy end_time back to due_date for homeworks
    op.execute("""
        UPDATE course_contents 
        SET due_date = end_time 
        WHERE (content_subtype = 'homework' OR content_type = 'assignment')
    """)
