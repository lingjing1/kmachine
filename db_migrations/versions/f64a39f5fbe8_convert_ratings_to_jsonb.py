"""convert_ratings_to_jsonb

Revision ID: f64a39f5fbe8
Revises: 19adf35f361a
Create Date: 2026-02-15 14:24:06.126325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f64a39f5fbe8'
down_revision: Union[str, Sequence[str], None] = '19adf35f361a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert ratings to JSONB and consolidate feedback."""
    # 0. Drop old check constraint that refers to the integer rating
    op.execute("ALTER TABLE material_ratings DROP CONSTRAINT IF EXISTS check_rating_range")

    # 1. Update generated_contents.teacher_rating
    # Using 'USING' clause to convert integer to jsonb object {"score": X}
    op.execute("""
        ALTER TABLE generated_contents 
        ALTER COLUMN teacher_rating TYPE JSONB 
        USING jsonb_build_object('score', teacher_rating)
    """)

    # 2. Update material_ratings
    # Merge 'rating' and 'feedback' into a single JSONB 'rating' column
    op.execute("""
        ALTER TABLE material_ratings 
        ALTER COLUMN rating TYPE JSONB 
        USING jsonb_build_object('score', rating, 'feedback', feedback)
    """)
    
    # 3. Drop redundant feedback column
    op.drop_column('material_ratings', 'feedback')


def downgrade() -> None:
    """Revert ratings to Integer and restore feedback column."""
    # 1. Restore material_ratings.feedback
    op.add_column('material_ratings', sa.Column('feedback', sa.Text(), nullable=True))
    
    # 2. Extract values from JSONB back to columns for material_ratings
    op.execute("""
        UPDATE material_ratings 
        SET feedback = rating->>'feedback',
            rating = (rating->>'score')::integer
    """)
    
    # 3. Change material_ratings.rating back to Integer
    op.execute("""
        ALTER TABLE material_ratings 
        ALTER COLUMN rating TYPE INTEGER 
        USING (rating->>'score')::integer
    """)

    # 4. Restore check constraint
    op.execute("ALTER TABLE material_ratings ADD CONSTRAINT check_rating_range CHECK ((rating >= 1) AND (rating <= 5))")

    # 5. Change generated_contents.teacher_rating back to Integer
    op.execute("""
        ALTER TABLE generated_contents 
        ALTER COLUMN teacher_rating TYPE INTEGER 
        USING (teacher_rating->>'score')::integer
    """)
