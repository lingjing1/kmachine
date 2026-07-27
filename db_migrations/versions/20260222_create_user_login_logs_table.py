"""create_user_login_logs_table

Revision ID: 20260222_login_logs
Revises: 20260218_metrics
Create Date: 2026-02-22 23:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260222_login_logs'
down_revision: Union[str, Sequence[str], None] = 'e552a0515078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'user_login_logs' not in tables:
        op.create_table(
            'user_login_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('role_id', sa.Integer(), nullable=True),
            sa.Column('logged_in_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        )
        op.create_index('idx_login_logs_user_id', 'user_login_logs', ['user_id'])
        op.create_index('idx_login_logs_logged_in_at', 'user_login_logs', ['logged_in_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_login_logs_logged_in_at', table_name='user_login_logs')
    op.drop_index('idx_login_logs_user_id', table_name='user_login_logs')
    op.drop_table('user_login_logs')
