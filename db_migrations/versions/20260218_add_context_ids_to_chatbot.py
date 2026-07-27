"""add attachment_id and content_id to student_chatbot_dialogs

Revision ID: 20260218_context_ids
Revises: d5829b8abde4
Create Date: 2026-02-18 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260218_context_ids'
down_revision: Union[str, Sequence[str], None] = 'd5829b8abde4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add attachment_id and content_id to student_chatbot_dialogs."""
    # attachment_id: 來自附件檢視器(上傳的教材)的對話
    op.add_column('student_chatbot_dialogs',
        sa.Column('attachment_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_chatbot_dialog_attachment',
        'student_chatbot_dialogs', 'attachments',
        ['attachment_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_chatbot_dialog_attachment',
        'student_chatbot_dialogs', ['attachment_id'])

    # content_id: 來自預習/複習/作業教材的對話
    op.add_column('student_chatbot_dialogs',
        sa.Column('content_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_chatbot_dialog_content',
        'student_chatbot_dialogs', 'course_contents',
        ['content_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_chatbot_dialog_content',
        'student_chatbot_dialogs', ['content_id'])


def downgrade() -> None:
    """Remove attachment_id and content_id from student_chatbot_dialogs."""
    op.drop_index('idx_chatbot_dialog_content', table_name='student_chatbot_dialogs')
    op.drop_constraint('fk_chatbot_dialog_content', 'student_chatbot_dialogs', type_='foreignkey')
    op.drop_column('student_chatbot_dialogs', 'content_id')

    op.drop_index('idx_chatbot_dialog_attachment', table_name='student_chatbot_dialogs')
    op.drop_constraint('fk_chatbot_dialog_attachment', 'student_chatbot_dialogs', type_='foreignkey')
    op.drop_column('student_chatbot_dialogs', 'attachment_id')
