"""increase page_numbers length to 255

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-01-15 14:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'r5s6t7u8v9w0'
down_revision: Union[str, Sequence[str], None] = 'q4r5s6t7u8v9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 增加 page_numbers 長度限制
    op.alter_column(
        'student_document_chunks',
        'page_numbers',
        type_=sa.String(255),
        existing_type=sa.String(100),
        existing_nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'student_document_chunks',
        'page_numbers',
        type_=sa.String(100),
        existing_type=sa.String(255),
        existing_nullable=True
    )
