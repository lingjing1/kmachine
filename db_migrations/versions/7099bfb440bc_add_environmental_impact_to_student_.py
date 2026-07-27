"""add_environmental_impact_to_student_chatbot_turn_logs

Revision ID: 7099bfb440bc
Revises: e27358e70c22
Create Date: 2026-03-12 15:26:01.005221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7099bfb440bc'
down_revision: Union[str, Sequence[str], None] = 'e27358e70c22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'student_chatbot_turn_logs',
        sa.Column(
            'environmental_impact',
            sa.dialects.postgresql.JSONB,
            nullable=True,
            comment='EcoLogits 碳排資料：energy_wh, gwp_kgco2eq 等環境指標'
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('student_chatbot_turn_logs', 'environmental_impact')
