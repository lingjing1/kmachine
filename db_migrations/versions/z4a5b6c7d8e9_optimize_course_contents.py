"""optimize course_contents schema

Revision ID: z4a5b6c7d8e9
Revises: z3a4b5c6d7e9
Create Date: 2026-02-06 16:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z4a5b6c7d8e9'
down_revision = '2c8b494181dc'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop description
    op.drop_column('course_contents', 'description')
    
    # 2. Drop is_published
    op.drop_column('course_contents', 'is_published')
    
    # 3. Drop knowledge_point_id
    # First drop FK and Index
    # Note: If these don't exist, it might fail. Only add if you are sure they exist.
    # Based on u8v9w0x1y2z3 migration:
    try:
        op.drop_constraint('fk_course_contents_kp_id', 'course_contents', type_='foreignkey')
    except Exception:
        pass # Ignore if strict constraint name match fails or doesn't exist

    try:
        op.drop_index('idx_course_contents_kp', table_name='course_contents')
    except Exception:
        pass

    op.drop_column('course_contents', 'knowledge_point_id')


def downgrade():
    # 1. Add description
    op.add_column('course_contents', sa.Column('description', sa.Text(), nullable=True))
    
    # 2. Add is_published
    op.add_column('course_contents', sa.Column('is_published', sa.Boolean(), server_default='false', nullable=True))
    
    # 3. Add knowledge_point_id
    op.add_column('course_contents', sa.Column('knowledge_point_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_course_contents_kp_id', 'course_contents', 'knowledge_points', ['knowledge_point_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_course_contents_kp', 'course_contents', ['knowledge_point_id'])
