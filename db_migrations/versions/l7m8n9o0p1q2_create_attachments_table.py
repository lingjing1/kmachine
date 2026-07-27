"""create attachments table

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-01-07 16:44:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'l7m8n9o0p1q2'
down_revision = 'k6l7m8n9o0p1'
branch_labels = None
depends_on = None


def upgrade():
    # 建立通用附件表
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attachable_type', sa.String(length=50), nullable=False),
        sa.Column('attachable_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('original_file_name', sa.String(length=255), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('file_type', sa.String(length=100), nullable=True),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.TIMESTAMP(timezone=True), server_default=sa.text("(NOW() AT TIME ZONE 'Asia/Taipei')"), nullable=True),
        sa.CheckConstraint("attachable_type IN ('announcement', 'unit', 'assignment', 'material')", name='attachments_type_check'),
        sa.CheckConstraint('file_size_bytes > 0 AND file_size_bytes <= 52428800', name='attachments_size_check'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('attachable_type', 'attachable_id', 'file_name', name='idx_attachments_unique')
    )
    
    # 建立索引以加速查詢
    op.create_index('idx_attachments_polymorphic', 'attachments', ['attachable_type', 'attachable_id'], unique=False)
    op.create_index('idx_attachments_uploader', 'attachments', ['uploaded_by'], unique=False)
    op.create_index('idx_attachments_created', 'attachments', [sa.text('uploaded_at DESC')], unique=False)


def downgrade():
    # 刪除索引
    op.drop_index('idx_attachments_created', table_name='attachments')
    op.drop_index('idx_attachments_uploader', table_name='attachments')
    op.drop_index('idx_attachments_polymorphic', table_name='attachments')
    
    # 刪除表
    op.drop_table('attachments')
