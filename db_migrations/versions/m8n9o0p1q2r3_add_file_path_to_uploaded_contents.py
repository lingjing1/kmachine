"""add file_path to uploaded_contents

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-01-08 17:40:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm8n9o0p1q2r3'
down_revision = 'l7m8n9o0p1q2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('uploaded_contents', sa.Column('file_path', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('uploaded_contents', 'file_path')
