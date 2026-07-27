"""add_knowledge_point_id_and_content_subtype_to_course_contents

Revision ID: u8v9w0x1y2z3
Revises: s7t8u9v0w1x2
Create Date: 2026-01-20 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'u8v9w0x1y2z3'
down_revision: Union[str, Sequence[str], None] = 's7t8u9v0w1x2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add knowledge_point_id column
    op.add_column('course_contents', sa.Column('knowledge_point_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_course_contents_kp_id', 'course_contents', 'knowledge_points', ['knowledge_point_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_course_contents_kp', 'course_contents', ['knowledge_point_id'])

    # Add content_subtype column
    op.add_column('course_contents', sa.Column('content_subtype', sa.String(50), nullable=True))
    op.create_index('idx_course_contents_subtype', 'course_contents', ['content_subtype'])


def downgrade() -> None:
    # Drop content_subtype column
    op.drop_index('idx_course_contents_subtype', table_name='course_contents')
    op.drop_column('course_contents', 'content_subtype')

    # Drop knowledge_point_id column
    op.drop_index('idx_course_contents_kp', table_name='course_contents')
    op.drop_constraint('fk_course_contents_kp_id', 'course_contents', type_='foreignkey')
    op.drop_column('course_contents', 'knowledge_point_id')
