"""create generator_setting_logs table

Revision ID: 00455374b949
Revises: fa02a5711d62
Create Date: 2026-03-06 01:44:43.509590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00455374b949'
down_revision: Union[str, Sequence[str], None] = 'fa02a5711d62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'generator_setting_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('orchestration_jobs.id'), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('section', sa.String(length=50), nullable=False), # prompt, source, kp
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('action_config', postgresql.JSONB(), server_default='{}'),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    # Add index for faster queries by user or session
    op.create_index('ix_gen_logs_user_session', 'generator_setting_logs', ['user_id', 'session_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('generator_setting_logs')
