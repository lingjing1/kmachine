"""add_student_unit_reports_table

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-01-24 14:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'z3a4b5c6d7e8'
down_revision = 'y2z3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('student_unit_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('preview_ai_explain', sa.Text(), nullable=True),
        sa.Column('review_ai_explain', sa.Text(), nullable=True),
        sa.Column('preview_highlights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('review_highlights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['course_units.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_student_unit_reports_student_unit', 'student_unit_reports', ['student_id', 'unit_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_student_unit_reports_student_unit', table_name='student_unit_reports')
    op.drop_table('student_unit_reports')
