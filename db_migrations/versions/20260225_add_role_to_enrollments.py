"""add_role_to_enrollments

Adds a 'role' column to the enrollments table to support per-course TA assignment.
Values: 'student' (default) or 'ta'.

Revision ID: 20260225_enrollments_role
Revises: 20260222_login_logs
Create Date: 2026-02-25 01:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260225_enrollments_role'
down_revision: Union[str, Sequence[str], None] = '41d70c7fe46e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add role column to enrollments table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if column already exists to make this idempotent
    columns = [col['name'] for col in inspector.get_columns('enrollments')]
    if 'role' not in columns:
        op.add_column(
            'enrollments',
            sa.Column(
                'role',
                sa.String(length=20),
                server_default='student',
                nullable=False
            )
        )

        op.create_check_constraint(
            'ck_enrollments_role',
            'enrollments',
            "role IN ('student', 'ta')"
        )

        op.create_index('idx_enrollments_role', 'enrollments', ['role'], unique=False)

        op.execute("COMMENT ON COLUMN enrollments.role IS '課程身份: student(學生) / ta(助教)'")


def downgrade() -> None:
    """Remove role column from enrollments table."""
    op.drop_index('idx_enrollments_role', table_name='enrollments')
    op.drop_constraint('ck_enrollments_role', 'enrollments', type_='check')
    op.drop_column('enrollments', 'role')
