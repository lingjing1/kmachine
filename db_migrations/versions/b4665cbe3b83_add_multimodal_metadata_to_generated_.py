"""add multimodal_metadata to generated_content_chunks

Revision ID: b4665cbe3b83
Revises: a1b2c3d4e5f7
Create Date: 2026-02-03 14:44:04.390932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b4665cbe3b83'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generated_content_chunks', sa.Column('multimodal_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generated_content_chunks', 'multimodal_metadata')
