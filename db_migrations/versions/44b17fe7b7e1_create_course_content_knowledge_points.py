"""create_course_content_knowledge_points

Revision ID: 44b17fe7b7e1
Revises: a4b5c6d7e8f9
Create Date: 2026-01-30 16:00:20.935309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44b17fe7b7e1'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create course_content_knowledge_points junction table
    op.create_table(
        'course_content_knowledge_points',
        sa.Column('course_content_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        
        sa.PrimaryKeyConstraint('course_content_id', 'knowledge_point_id'),
        
        sa.ForeignKeyConstraint(
            ['course_content_id'], 
            ['course_contents.id'],
            name='fk_cckp_content',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['knowledge_point_id'], 
            ['knowledge_points.id'],
            name='fk_cckp_kp',
            ondelete='CASCADE'
        )
    )
    
    # Create indexes for performance
    op.create_index(
        'idx_cckp_content', 
        'course_content_knowledge_points', 
        ['course_content_id']
    )
    op.create_index(
        'idx_cckp_kp', 
        'course_content_knowledge_points', 
        ['knowledge_point_id']
    )


def downgrade() -> None:
    op.drop_index('idx_cckp_kp', table_name='course_content_knowledge_points')
    op.drop_index('idx_cckp_content', table_name='course_content_knowledge_points')
    op.drop_table('course_content_knowledge_points')
