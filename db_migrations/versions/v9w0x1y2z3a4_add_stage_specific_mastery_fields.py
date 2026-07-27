"""add_stage_specific_mastery_fields

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-01-21 10:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v9w0x1y2z3a4'
down_revision: Union[str, Sequence[str], None] = 'u8v9w0x1y2z3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add preview-specific fields
    op.add_column('student_knowledge_mastery', 
                  sa.Column('preview_mastery_level', sa.String(50), nullable=True))
    op.add_column('student_knowledge_mastery', 
                  sa.Column('preview_confidence', sa.Float(), nullable=True))
    op.add_column('student_knowledge_mastery', 
                  sa.Column('preview_lime_report_path', sa.String(500), nullable=True))
    
    # Add review-specific fields
    op.add_column('student_knowledge_mastery', 
                  sa.Column('review_mastery_level', sa.String(50), nullable=True))
    op.add_column('student_knowledge_mastery', 
                  sa.Column('review_confidence', sa.Float(), nullable=True))
    op.add_column('student_knowledge_mastery', 
                  sa.Column('review_lime_report_path', sa.String(500), nullable=True))
    
    # Migrate existing mastery_level to preview_mastery_level for records with preview_completed=true
    op.execute("""
        UPDATE student_knowledge_mastery 
        SET preview_mastery_level = mastery_level 
        WHERE preview_completed = true AND preview_mastery_level IS NULL
    """)
    
    # Migrate existing mastery_level to review_mastery_level for records with review_completed=true
    op.execute("""
        UPDATE student_knowledge_mastery 
        SET review_mastery_level = mastery_level 
        WHERE review_completed = true AND review_mastery_level IS NULL
    """)


def downgrade() -> None:
    # Drop review-specific fields
    op.drop_column('student_knowledge_mastery', 'review_lime_report_path')
    op.drop_column('student_knowledge_mastery', 'review_confidence')
    op.drop_column('student_knowledge_mastery', 'review_mastery_level')
    
    # Drop preview-specific fields
    op.drop_column('student_knowledge_mastery', 'preview_lime_report_path')
    op.drop_column('student_knowledge_mastery', 'preview_confidence')
    op.drop_column('student_knowledge_mastery', 'preview_mastery_level')
