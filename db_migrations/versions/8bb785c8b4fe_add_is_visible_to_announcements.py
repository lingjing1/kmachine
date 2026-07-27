"""add_is_visible_to_announcements

Revision ID: 8bb785c8b4fe
Revises: 026082a170a5
Create Date: 2026-03-03 17:06:48.238933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bb785c8b4fe'
down_revision: Union[str, Sequence[str], None] = '026082a170a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('course_announcements', sa.Column('is_visible', sa.Boolean(), nullable=True, server_default='true'))
    # Update existing rows to be visible
    op.execute("UPDATE course_announcements SET is_visible = true WHERE is_visible IS NULL")
    # Change nullable to False after updating existing rows
    op.alter_column('course_announcements', 'is_visible', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('course_announcements', 'is_visible')
