"""add_model_name_to_student_chatbot_turn_logs

Revision ID: 7346d6cabaec
Revises: 7099bfb440bc
Create Date: 2026-03-12 17:35:19.559233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7346d6cabaec'
down_revision: Union[str, Sequence[str], None] = '7099bfb440bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add model_name column."""
    op.add_column(
        'student_chatbot_turn_logs',
        sa.Column(
            'model_name',
            sa.String(100),
            nullable=True,
            comment='LLM 模型名稱，如 gpt-4o-mini'
        )
    )


def downgrade() -> None:
    """Remove model_name column."""
    op.drop_column('student_chatbot_turn_logs', 'model_name')
