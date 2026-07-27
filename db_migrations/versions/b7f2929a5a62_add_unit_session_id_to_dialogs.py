"""add_unit_session_id_to_dialogs

Revision ID: b7f2929a5a62
Revises: 20260305_1825_preview
Create Date: 2026-03-05 19:48:48.406275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f2929a5a62'
down_revision: Union[str, Sequence[str], None] = '20260305_1825_preview'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('student_chatbot_dialogs', sa.Column('unit_session_id', sa.UUID(), nullable=True))
    op.create_index('idx_scd_session', 'student_chatbot_dialogs', ['unit_session_id'])


def downgrade() -> None:
    op.drop_index('idx_scd_session', table_name='student_chatbot_dialogs')
    op.drop_column('student_chatbot_dialogs', 'unit_session_id')
