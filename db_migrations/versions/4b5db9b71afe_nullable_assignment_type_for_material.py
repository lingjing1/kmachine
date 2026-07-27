"""nullable assignment_type for material

Revision ID: 4b5db9b71afe
Revises: b48b2fc71963
Create Date: 2026-02-25 15:51:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Alembic 版本識別碼
revision: str = '4b5db9b71afe'
down_revision: Union[str, Sequence[str], None] = 'b48b2fc71963'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    讓 assignment_type 欄位可為 NULL，並將 material 類型的資料設為 NULL。
    - material 類型：assignment_type 無語意意義 → 設為 NULL
    - exam 類型：保留 'questions' 或 'file_upload' 不變
    """
    # 1. 先移除 NOT NULL 約束和 server_default（必須先做，否則 UPDATE SET NULL 會違反約束）
    op.alter_column(
        'course_contents',
        'assignment_type',
        existing_type=sa.String(20),
        nullable=True,
        server_default=None,
    )

    # 2. 將所有 material 類型的 assignment_type 改為 NULL
    op.execute("""
        UPDATE course_contents
        SET assignment_type = NULL
        WHERE content_type = 'material'
    """)


def downgrade() -> None:
    """
    還原 assignment_type 為 NOT NULL，並重設 server_default 為 'questions'。
    """
    # 先將 NULL 值還原為 'questions'，以滿足 NOT NULL 約束
    op.execute("""
        UPDATE course_contents
        SET assignment_type = 'questions'
        WHERE assignment_type IS NULL
    """)

    op.alter_column(
        'course_contents',
        'assignment_type',
        existing_type=sa.String(20),
        nullable=False,
        server_default='questions',
    )
