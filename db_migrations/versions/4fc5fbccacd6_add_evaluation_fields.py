"""add_evaluation_fields

Revision ID: 4fc5fbccacd6
Revises: cd58a297e31d
Create Date: 2026-03-18 15:58:01.120571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fc5fbccacd6'
down_revision: Union[str, Sequence[str], None] = 'cd58a297e31d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('exp_generated_contents', sa.Column('course_name', sa.String(length=255), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('total_cost_usd', sa.Float(), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('total_cost_twd', sa.Float(), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('environmental_impact', sa.JSON(), nullable=True))
    op.add_column('exp_generated_contents', sa.Column('is_selected_for_eval', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    op.create_table(
        'exp_human_evaluations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('exp_generated_content_id', sa.Integer(), sa.ForeignKey('exp_generated_contents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewer_name', sa.String(length=255), nullable=True),
        sa.Column('human_fact_score', sa.Integer(), nullable=True),
        sa.Column('human_quality_scores', sa.JSON(), nullable=True),
        sa.Column('llm_agreement_status', sa.String(length=50), nullable=True),
        sa.Column('llm_agreement_feedback', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('exp_human_evaluations')
    op.drop_column('exp_generated_contents', 'is_selected_for_eval')
    op.drop_column('exp_generated_contents', 'environmental_impact')
    op.drop_column('exp_generated_contents', 'total_cost_twd')
    op.drop_column('exp_generated_contents', 'total_cost_usd')
    op.drop_column('exp_generated_contents', 'course_name')
