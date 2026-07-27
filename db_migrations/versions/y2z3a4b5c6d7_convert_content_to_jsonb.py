
"""convert_content_to_jsonb

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-01-24 18:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'y2z3a4b5c6d7'
down_revision = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    # Convert content column from JSON to JSONB
    op.alter_column('course_contents', 'content',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               postgresql_using='content::jsonb',
               existing_nullable=True)


def downgrade():
    # Convert content column back from JSONB to JSON
    op.alter_column('course_contents', 'content',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=postgresql.JSON(astext_type=sa.Text()),
               postgresql_using='content::json',
               existing_nullable=True)
