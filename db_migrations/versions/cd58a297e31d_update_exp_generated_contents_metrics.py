"""update_exp_generated_contents_metrics

Revision ID: cd58a297e31d
Revises: 2ee1b01dcbce
Create Date: 2026-03-17 18:02:16.614820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd58a297e31d'
down_revision: Union[str, Sequence[str], None] = '2ee1b01dcbce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Upgrade schema
    op.drop_column('exp_generated_contents', 'title')
    op.drop_column('exp_generated_contents', 'prompt')
    
    op.add_column('exp_generated_contents', sa.Column('rag_metrics', postgresql.JSONB(), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('critic_scores', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Downgrade schema
    op.drop_column('exp_generated_contents', 'critic_scores')
    op.drop_column('exp_generated_contents', 'rag_metrics')
    
    op.add_column('exp_generated_contents', sa.Column('prompt', sa.Text(), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('title', sa.String(255), nullable=True))
