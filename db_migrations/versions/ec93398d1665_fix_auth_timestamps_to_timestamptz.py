"""fix_auth_timestamps_to_timestamptz

Revision ID: ec93398d1665
Revises: 20260222_login_logs
Create Date: 2026-02-23 22:00:10.302536

變更說明:
將註冊/登入相關表的 TIMESTAMP 欄位統一改為 TIMESTAMP WITH TIME ZONE，
確保時區安全，與 user_login_logs 等較新表的風格一致。

影響的表與欄位:
1. email_verifications: created_at, expires_at
2. users: approved_at
3. teacher_profiles: created_at, updated_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec93398d1665'
down_revision: Union[str, Sequence[str], None] = '20260222_login_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需要修改的欄位清單: (表名, 欄位名, server_default)
COLUMNS_TO_ALTER = [
    ('email_verifications', 'created_at', sa.text('NOW()')),
    ('email_verifications', 'expires_at', None),
    ('users', 'approved_at', None),
    ('teacher_profiles', 'created_at', sa.text('NOW()')),
    ('teacher_profiles', 'updated_at', sa.text('NOW()')),
]


def upgrade() -> None:
    """將 TIMESTAMP 改為 TIMESTAMP WITH TIME ZONE"""
    for table, column, server_default in COLUMNS_TO_ALTER:
        kwargs = {
            'existing_type': sa.TIMESTAMP(),
            'type_': sa.TIMESTAMP(timezone=True),
        }
        if server_default is not None:
            kwargs['existing_server_default'] = server_default
        op.alter_column(table, column, **kwargs)


def downgrade() -> None:
    """將 TIMESTAMP WITH TIME ZONE 改回 TIMESTAMP"""
    for table, column, server_default in COLUMNS_TO_ALTER:
        kwargs = {
            'existing_type': sa.TIMESTAMP(timezone=True),
            'type_': sa.TIMESTAMP(),
        }
        if server_default is not None:
            kwargs['existing_server_default'] = server_default
        op.alter_column(table, column, **kwargs)

