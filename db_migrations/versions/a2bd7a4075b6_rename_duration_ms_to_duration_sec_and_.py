"""rename duration_ms to duration_sec and change to float

Revision ID: a2bd7a4075b6
Revises: 00455374b949
Create Date: 2026-03-06 02:33:55.544186

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2bd7a4075b6'
down_revision: Union[str, Sequence[str], None] = '00455374b949'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename column
    op.alter_column('generator_setting_logs', 'duration_ms', new_column_name='duration_sec', type_=sa.Float(), postgresql_using='duration_ms::float / 1000.0')


def downgrade() -> None:
    """Downgrade schema."""
    # Rename column back
    op.alter_column('generator_setting_logs', 'duration_sec', new_column_name='duration_ms', type_=sa.Integer(), postgresql_using='duration_sec::integer * 1000')
