"""add_ablation_study_tables

Revision ID: 2ee1b01dcbce
Revises: 7346d6cabaec
Create Date: 2026-03-17 16:24:57.213056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ee1b01dcbce'
down_revision: Union[str, Sequence[str], None] = '7346d6cabaec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create exp_seed_configs
    op.create_table(
        'exp_seed_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('course_name', sa.String(255), nullable=True),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('input_config', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('original_job_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )

    # 2. Create exp_generated_contents
    op.create_table(
        'exp_generated_contents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ablation_group', sa.String(50), nullable=False),
        sa.Column('seed_config_id', sa.Integer(), sa.ForeignKey('exp_seed_configs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_id', sa.String(100), nullable=False),
        sa.Column('content_type', sa.String(50), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )

    # 3. Add ablation_group to existing tables
    op.add_column('generated_contents', sa.Column('ablation_group', sa.String(50), nullable=True))
    op.add_column('generator_setting_logs', sa.Column('ablation_group', sa.String(50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Remove columns from existing tables
    op.drop_column('generator_setting_logs', 'ablation_group')
    op.drop_column('generated_contents', 'ablation_group')

    # 2. Drop new tables
    op.drop_table('exp_generated_contents')
    op.drop_table('exp_seed_configs')
