"""standardize_score_and_grade_json

Revision ID: 6176edc30ce4
Revises: z5a6b7c8d9e0
Create Date: 2026-02-10 17:05:10.180789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6176edc30ce4'
down_revision: Union[str, Sequence[str], None] = 'z5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. submissions_assignment
    # Add 'score' column (Float)
    op.add_column('submissions_assignment', sa.Column('score', sa.Float(), nullable=True))
    
    # Migrate data: copy 'grade' (Numeric) to 'score' (Float)
    op.execute("UPDATE submissions_assignment SET score = grade")
    
    # Clear 'grade' column safely before converting to JSON
    # Assuming we don't need to keep the old numeric value in 'grade' since it's now in 'score'
    op.execute("UPDATE submissions_assignment SET grade = NULL")
    
    # Alter 'grade' column to JSON
    op.alter_column('submissions_assignment', 'grade',
               existing_type=sa.Numeric(),
               type_=sa.JSON(),
               postgresql_using='grade::text::jsonb',
               nullable=True)

    # 2. submissions_exam
    # Alter 'grade' column from String to JSON
    # First clear it to avoid casting errors if random strings exist
    op.execute("UPDATE submissions_exam SET grade = NULL")
    op.alter_column('submissions_exam', 'grade',
               existing_type=sa.String(length=10),
               type_=sa.JSON(),
               postgresql_using='grade::jsonb',
               nullable=True)

    # Alter 'score' column from Numeric to Float (for consistency if desired)
    op.alter_column('submissions_exam', 'score',
               existing_type=sa.Numeric(),
               type_=sa.Float(),
               nullable=True)


def downgrade() -> None:
    # 1. submissions_exam
    # Revert 'score' to Numeric
    op.alter_column('submissions_exam', 'score',
               existing_type=sa.Float(),
               type_=sa.Numeric(),
               nullable=True)

    # Revert 'grade' to String
    op.alter_column('submissions_exam', 'grade',
               existing_type=sa.JSON(),
               type_=sa.String(length=10),
               postgresql_using='grade::text',
               nullable=True)

    # 2. submissions_assignment
    # Revert 'grade' to Numeric (This will lose JSON data if not handled, but downgrade is destructive usually)
    # We can try to copy 'score' back to 'grade' if we want to restore previous state
    op.execute("UPDATE submissions_assignment SET grade = NULL")
    op.alter_column('submissions_assignment', 'grade',
               existing_type=sa.JSON(),
               type_=sa.Numeric(),
               postgresql_using='grade::text::numeric',
               nullable=True)
    
    # Copy score back to grade
    op.execute("UPDATE submissions_assignment SET grade = score")

    # Drop 'score' column
    op.drop_column('submissions_assignment', 'score')
