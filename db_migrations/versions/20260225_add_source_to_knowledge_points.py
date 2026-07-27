"""add_source_to_knowledge_points

Add source_type, source_name, and source_id columns to the knowledge_points table
to track whether a KP was created manually by a teacher or promoted from a
document extraction (document_knowledge_points).

Revision ID: 20260225_kp_source
Revises: 4b5db9b71afe
Create Date: 2026-02-25 19:41:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '20260225_kp_source'
down_revision: Union[str, Sequence[str], None] = '4b5db9b71afe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [col['name'] for col in inspector.get_columns('knowledge_points')]

    if 'source_type' not in existing_cols:
        op.add_column(
            'knowledge_points',
            sa.Column(
                'source_type',
                sa.String(length=20),
                server_default='manual',
                nullable=False
            )
        )
        op.create_check_constraint(
            'ck_kp_source_type',
            'knowledge_points',
            "source_type IN ('extracted', 'manual')"
        )
        op.execute(
            "COMMENT ON COLUMN knowledge_points.source_type IS "
            "'extracted: promoted from document extraction; manual: teacher-created'"
        )

    if 'source_name' not in existing_cols:
        op.add_column(
            'knowledge_points',
            sa.Column('source_name', sa.String(length=200), nullable=True)
        )
        op.execute(
            "COMMENT ON COLUMN knowledge_points.source_name IS "
            "'Display name of the origin: file name or manual'"
        )

    if 'source_id' not in existing_cols:
        op.add_column(
            'knowledge_points',
            sa.Column('source_id', sa.Integer(), nullable=True)
        )
        op.execute(
            "COMMENT ON COLUMN knowledge_points.source_id IS "
            "'unique_content_id of the source document when source_type=extracted'"
        )

    op.create_index(
        'idx_kp_source_type',
        'knowledge_points',
        ['source_type']
    )


def downgrade() -> None:
    op.drop_index('idx_kp_source_type', table_name='knowledge_points')
    op.drop_constraint('ck_kp_source_type', 'knowledge_points', type_='check')
    op.drop_column('knowledge_points', 'source_id')
    op.drop_column('knowledge_points', 'source_name')
    op.drop_column('knowledge_points', 'source_type')
