"""create_document_knowledge_points

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-01-27 11:30:00.000000

Enhanced schema to support:
1. Hierarchical KP structure (Big Ideas -> Sub-concepts)
2. Relationship types between KPs (prerequisite, composition, contrast)
3. Mermaid graph metadata for visualization
4. Can-do statements for educational outcomes
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'z3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create document_knowledge_points table
    op.create_table(
        'document_knowledge_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('unique_content_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False, comment='Teacher who created/customized this KP map'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1', comment='Version number for regeneration tracking'),
        sa.Column('knowledge_point_name', sa.String(200), nullable=False),
        sa.Column('kp_description', sa.Text(), nullable=True, comment='Can-do statement or ability description'),
        sa.Column('kp_level', sa.String(20), nullable=True, comment='Level: big_idea, core_concept, sub_technique'),
        sa.Column('parent_kp_id', sa.Integer(), nullable=True, comment='Parent KP for hierarchical structure'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('mermaid_node_id', sa.String(10), nullable=True, comment='Node ID in Mermaid graph (e.g., A, B, C)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='False if teacher regenerated and replaced'),
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('modified_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['unique_content_id'], 
            ['unique_contents.id'],
            name='fk_doc_kp_unique_content',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['teacher_id'],
            ['users.id'],
            name='fk_doc_kp_teacher',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['parent_kp_id'],
            ['document_knowledge_points.id'],
            name='fk_doc_kp_parent',
            ondelete='CASCADE'
        ),
        sa.CheckConstraint(
            "kp_level IN ('big_idea', 'core_concept', 'sub_technique') OR kp_level IS NULL",
            name='valid_kp_level'
        )
    )
    
    # Create relationship table for KP connections
    op.create_table(
        'document_kp_relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('unique_content_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False, comment='Matches teacher_id from document_knowledge_points'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('from_kp_id', sa.Integer(), nullable=False),
        sa.Column('to_kp_id', sa.Integer(), nullable=False),
        sa.Column('relationship_type', sa.String(20), nullable=False, comment='Type: prerequisite, composition, contrast, extension'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['unique_content_id'],
            ['unique_contents.id'],
            name='fk_kp_rel_content',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['teacher_id'],
            ['users.id'],
            name='fk_kp_rel_teacher',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['from_kp_id'],
            ['document_knowledge_points.id'],
            name='fk_kp_rel_from',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['to_kp_id'],
            ['document_knowledge_points.id'],
            name='fk_kp_rel_to',
            ondelete='CASCADE'
        ),
        sa.CheckConstraint(
            "relationship_type IN ('prerequisite', 'composition', 'contrast', 'extension')",
            name='valid_relationship_type'
        ),
        sa.UniqueConstraint('from_kp_id', 'to_kp_id', 'relationship_type', name='unique_kp_relationship')
    )
    
    # Create indexes for document_knowledge_points
    op.create_index(
        'idx_doc_kp_content_id', 
        'document_knowledge_points', 
        ['unique_content_id']
    )
    op.create_index(
        'idx_doc_kp_teacher_content',
        'document_knowledge_points',
        ['teacher_id', 'unique_content_id', 'version']
    )
    op.create_index(
        'idx_doc_kp_active',
        'document_knowledge_points',
        ['is_active']
    )
    op.create_index(
        'idx_doc_kp_confidence', 
        'document_knowledge_points', 
        ['confidence_score'],
        postgresql_ops={'confidence_score': 'DESC'}
    )
    op.create_index(
        'idx_doc_kp_parent',
        'document_knowledge_points',
        ['parent_kp_id']
    )
    op.create_index(
        'idx_doc_kp_level',
        'document_knowledge_points',
        ['kp_level']
    )
    
    # Create indexes for relationships
    op.create_index(
        'idx_kp_rel_from',
        'document_kp_relationships',
        ['from_kp_id']
    )
    op.create_index(
        'idx_kp_rel_to',
        'document_kp_relationships',
        ['to_kp_id']
    )
    op.create_index(
        'idx_kp_rel_teacher_content',
        'document_kp_relationships',
        ['teacher_id', 'unique_content_id', 'version']
    )


def downgrade() -> None:
    # Drop relationship table indexes
    op.drop_index('idx_kp_rel_teacher_content', table_name='document_kp_relationships')
    op.drop_index('idx_kp_rel_to', table_name='document_kp_relationships')
    op.drop_index('idx_kp_rel_from', table_name='document_kp_relationships')
    
    # Drop KP table indexes
    op.drop_index('idx_doc_kp_level', table_name='document_knowledge_points')
    op.drop_index('idx_doc_kp_parent', table_name='document_knowledge_points')
    op.drop_index('idx_doc_kp_confidence', table_name='document_knowledge_points')
    op.drop_index('idx_doc_kp_active', table_name='document_knowledge_points')
    op.drop_index('idx_doc_kp_teacher_content', table_name='document_knowledge_points')
    op.drop_index('idx_doc_kp_content_id', table_name='document_knowledge_points')
    
    # Drop tables
    op.drop_table('document_kp_relationships')
    op.drop_table('document_knowledge_points')


