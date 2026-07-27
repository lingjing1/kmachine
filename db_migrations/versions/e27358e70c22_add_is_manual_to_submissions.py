"""add_is_manual_to_submissions

Revision ID: e27358e70c22
Revises: 2e708246ce23
Create Date: 2026-03-10 17:32:22.274788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e27358e70c22'
down_revision: Union[str, Sequence[str], None] = '2e708246ce23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('submissions_assignment', sa.Column('is_manual', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('submissions_exam', sa.Column('is_manual', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('submissions_exam', 'is_manual')
    op.drop_column('submissions_assignment', 'is_manual')
