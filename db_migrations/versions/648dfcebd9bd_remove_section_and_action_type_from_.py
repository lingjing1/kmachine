"""remove_section_and_action_type_from_generator_setting_logs

Revision ID: 648dfcebd9bd
Revises: a2bd7a4075b6
Create Date: 2026-03-06 04:03:19.239368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '648dfcebd9bd'
down_revision: Union[str, Sequence[str], None] = 'a2bd7a4075b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('generator_setting_logs', 'section')
    op.drop_column('generator_setting_logs', 'action_type')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('generator_setting_logs', sa.Column('action_type', sa.String(length=100), server_default=sa.text("'default'::character varying"), autoincrement=False, nullable=False))
    op.add_column('generator_setting_logs', sa.Column('section', sa.String(length=50), server_default=sa.text("'default'::character varying"), autoincrement=False, nullable=False))
