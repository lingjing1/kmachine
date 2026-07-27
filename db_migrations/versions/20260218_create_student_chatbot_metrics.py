"""create_student_chatbot_metrics

Revision ID: 20260218_metrics
Revises: 20260218_context_ids
Create Date: 2026-02-18 23:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260218_metrics'
down_revision: Union[str, Sequence[str], None] = '20260218_context_ids'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create student_chatbot_metrics table
    op.create_table(
        'student_chatbot_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dialog_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=50), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('estimated_cost_usd', sa.Numeric(precision=12, scale=10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dialog_id', name='uq_chatbot_metrics_dialog_id')
    )
    
    # Add foreign key
    op.create_foreign_key(
        'fk_chat_metrics_dialog',
        'student_chatbot_metrics', 'student_chatbot_dialogs',
        ['dialog_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Add index for conversation_id
    op.create_index('idx_chat_metrics_conversation', 'student_chatbot_metrics', ['conversation_id'])


def downgrade() -> None:
    op.drop_table('student_chatbot_metrics')
