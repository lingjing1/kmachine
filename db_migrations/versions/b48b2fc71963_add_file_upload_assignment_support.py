"""add file upload assignment support

Revision ID: b48b2fc71963
Revises: 20260225_enrollments_role
Create Date: 2026-02-25 13:29:00.946649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b48b2fc71963'
down_revision: Union[str, Sequence[str], None] = '20260225_enrollments_role'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add file upload assignment support."""

    # 1. course_contents: add assignment_type and description
    op.add_column('course_contents', sa.Column(
        'assignment_type',
        sa.String(20),
        nullable=False,
        server_default='questions',
        comment="Assignment submission type: 'questions' or 'file_upload'"
    ))
    op.add_column('course_contents', sa.Column(
        'description',
        sa.Text(),
        nullable=True,
        comment="Assignment description (supports Markdown)"
    ))

    # Check constraint for valid assignment_type values
    op.create_check_constraint(
        'ck_course_contents_assignment_type',
        'course_contents',
        "assignment_type IN ('questions', 'file_upload')"
    )

    # 2. submissions_assignment: add file-related columns
    op.add_column('submissions_assignment', sa.Column(
        'file_name', sa.String(500), nullable=True,
        comment="Stored filename (hashed)"
    ))
    op.add_column('submissions_assignment', sa.Column(
        'original_file_name', sa.String(500), nullable=True,
        comment="Original filename from upload"
    ))
    op.add_column('submissions_assignment', sa.Column(
        'file_path', sa.String(1000), nullable=True,
        comment="Server file storage path"
    ))
    op.add_column('submissions_assignment', sa.Column(
        'file_size_bytes', sa.BigInteger(), nullable=True,
        comment="File size in bytes"
    ))
    op.add_column('submissions_assignment', sa.Column(
        'file_type', sa.String(100), nullable=True,
        comment="MIME type of uploaded file"
    ))


def downgrade() -> None:
    """Remove file upload assignment support."""

    # Remove file columns from submissions_assignment
    op.drop_column('submissions_assignment', 'file_type')
    op.drop_column('submissions_assignment', 'file_size_bytes')
    op.drop_column('submissions_assignment', 'file_path')
    op.drop_column('submissions_assignment', 'original_file_name')
    op.drop_column('submissions_assignment', 'file_name')

    # Remove assignment columns from course_contents
    op.drop_constraint('ck_course_contents_assignment_type', 'course_contents', type_='check')
    op.drop_column('course_contents', 'description')
    op.drop_column('course_contents', 'assignment_type')
