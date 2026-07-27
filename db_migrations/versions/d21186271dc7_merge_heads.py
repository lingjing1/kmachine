"""merge heads

Revision ID: d21186271dc7
Revises: 6176edc30ce4, c1d038e2cd59
Create Date: 2026-02-11 20:04:40.340562

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd21186271dc7'
down_revision: Union[str, Sequence[str], None] = ('6176edc30ce4', 'c1d038e2cd59')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
