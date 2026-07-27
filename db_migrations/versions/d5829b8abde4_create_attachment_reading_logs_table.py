"""create_attachment_reading_logs_table

Revision ID: d5829b8abde4
Revises: 20260216_time_tracking
Create Date: 2026-02-17 23:35:50.715928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5829b8abde4'
down_revision: Union[str, Sequence[str], None] = '20260216_time_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'attachment_reading_logs' not in tables:
        op.create_table(
            'attachment_reading_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('attachment_id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('reading_time_seconds', sa.Integer(), server_default='0', nullable=True),
            sa.Column('last_read_at', sa.DateTime(), server_default=sa.text("(NOW() AT TIME ZONE 'Asia/Taipei')"), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['attachment_id'], ['attachments.id'], ),
            sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
            sa.UniqueConstraint('attachment_id', 'student_id')
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('attachment_reading_logs')
