"""20260305_1825_add_source_preview_logs

Add source_preview_logs JSONB column to both generated_contents and course_contents
to record every instance of a teacher opening a RAG source reference panel, which
source_id was viewed, and how long the session lasted.

This supports analysis of:
- Trust: did the teacher verify AI content against source material?
- RAG effectiveness: were references consulted before accepting or editing content?
- Behavior segmentation: view-only vs view-then-edit vs no-view-and-save

Revision ID: 20260305_1825_source_preview_logs
Revises: 20260305_1715_add_edit_history
Create Date: 2026-03-05 18:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260305_1825_preview'
down_revision: Union[str, Sequence[str], None] = '20260305_1715_add_edit_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_preview_logs to generated_contents
    # Captures preview behavior during the initial AI generation review phase.
    # Format: [{ source_id, chunk_id, view_start, view_seconds }, ...]
    op.add_column(
        'generated_contents',
        sa.Column(
            'source_preview_logs',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='List of source preview interactions during AI content review. '
                    'Each entry: {source_id, chunk_id, view_start, view_seconds}'
        )
    )

    # Add source_preview_logs to course_contents
    # Captures preview behavior during the course content editing phase (after first save).
    # Format: [{ source_id, chunk_id, view_start, view_seconds }, ...]
    op.add_column(
        'course_contents',
        sa.Column(
            'source_preview_logs',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='List of source preview interactions when editing published course content. '
                    'Each entry: {source_id, chunk_id, view_start, view_seconds}'
        )
    )


def downgrade() -> None:
    op.drop_column('course_contents', 'source_preview_logs')
    op.drop_column('generated_contents', 'source_preview_logs')
