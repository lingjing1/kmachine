"""submissions_assignment_timestamp_to_timestamptz

Revision ID: 026082a170a5
Revises: 20260225_kp_source
Create Date: 2026-02-25 19:55:32.735048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '026082a170a5'
down_revision: Union[str, Sequence[str], None] = '20260225_kp_source'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需要從 timestamp -> timestamptz 的欄位
_TABLE = "submissions_assignment"
_COLUMNS = ["submitted_at", "updated_at", "started_at"]


def upgrade() -> None:
    """將 submissions_assignment 的時間欄位從 timestamp 改為 timestamptz。
    
    現有資料視為 UTC，USING 子句會自動加上 +00 時區。
    """
    for col in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_TABLE} '
            f'ALTER COLUMN {col} TYPE TIMESTAMPTZ '
            f'USING {col} AT TIME ZONE \'UTC\''
        )


def downgrade() -> None:
    """還原為 timestamp（移除時區資訊）。"""
    for col in _COLUMNS:
        op.execute(
            f'ALTER TABLE {_TABLE} '
            f'ALTER COLUMN {col} TYPE TIMESTAMP '
            f'USING {col} AT TIME ZONE \'UTC\''
        )
