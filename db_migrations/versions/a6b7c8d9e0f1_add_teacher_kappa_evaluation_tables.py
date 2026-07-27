"""add_teacher_kappa_evaluation_tables

Revision ID: a6b7c8d9e0f1
Revises: 55c56739386d
Create Date: 2026-04-21 10:00:00.000000

建立教師 Kappa 評估四張表（一任務一表，無 FK，每 row 自包含 snapshot）：
- teacher_eval_course62_mastery     : Task A  RoBERTa 掌握度 vs 教師
- teacher_eval_course62_polarity    : Task B  LIME 關鍵字極性 vs 教師
- teacher_eval_finetune_mastery     : Task C1 CSV Mastery_Label vs 教師
- teacher_eval_finetune_performance : Task C2 CSV 學生表現 vs 教師
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, Sequence[str], None] = '55c56739386d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== Task A: course62 mastery (RoBERTa vs teacher) =====
    op.create_table(
        'teacher_eval_course62_mastery',
        sa.Column('id', sa.Integer(), primary_key=True),
        # --- 來源引用（surrogate + 自然鍵三層保險） ---
        sa.Column('history_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('source_stage', sa.String(16), nullable=True),
        sa.Column('source_assessed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        # --- 抽樣 / 呈現 ---
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('stratum', sa.String(16), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        # --- AI 原始預測 ---
        sa.Column('ai_mastery', sa.String(16), nullable=False),
        sa.Column('ai_mastery_confidence', sa.Float(), nullable=True),
        # --- 完整快照 ---
        sa.Column('lime_report_json', postgresql.JSONB(), nullable=False),
        # --- 教師評分 ---
        sa.Column('teacher_mastery', sa.String(16), nullable=True),
        sa.Column('teacher_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('history_id', 'teacher_id', name='uq_eval_a_history_teacher'),
    )
    op.create_index('idx_eval_a_teacher', 'teacher_eval_course62_mastery', ['teacher_id', 'display_order'])

    # ===== Task B: course62 LIME polarity =====
    op.create_table(
        'teacher_eval_course62_polarity',
        sa.Column('id', sa.Integer(), primary_key=True),
        # --- 來源引用（與 Task A 同一筆 history 對應） ---
        sa.Column('history_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.Column('source_stage', sa.String(16), nullable=True),
        sa.Column('source_assessed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        # --- 抽樣 / 呈現 ---
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('stratum', sa.String(16), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        # --- 完整快照 + AI 極性 ---
        sa.Column('lime_report_json', postgresql.JSONB(), nullable=False),
        sa.Column('ai_polarities', postgresql.JSONB(), nullable=False),
        # --- 教師評分 ---
        sa.Column('teacher_polarities', postgresql.JSONB(), nullable=True),
        sa.Column('teacher_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('history_id', 'teacher_id', name='uq_eval_b_history_teacher'),
    )
    op.create_index('idx_eval_b_teacher', 'teacher_eval_course62_polarity', ['teacher_id', 'display_order'])

    # ===== Task C1: finetune mastery =====
    op.create_table(
        'teacher_eval_finetune_mastery',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_ref', sa.String(64), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('stratum', sa.String(16), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('csv_row', postgresql.JSONB(), nullable=False),
        sa.Column('ai_mastery', sa.String(16), nullable=False),
        sa.Column('teacher_mastery', sa.String(16), nullable=True),
        sa.Column('teacher_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('source_ref', 'teacher_id', name='uq_eval_c1_ref_teacher'),
    )
    op.create_index('idx_eval_c1_teacher', 'teacher_eval_finetune_mastery', ['teacher_id', 'display_order'])

    # ===== Task C2: finetune performance (per-question) =====
    op.create_table(
        'teacher_eval_finetune_performance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_ref', sa.String(64), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('stratum', sa.String(32), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('question_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('ai_performance', sa.String(32), nullable=False),
        sa.Column('teacher_performance', sa.String(32), nullable=True),
        sa.Column('teacher_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('source_ref', 'teacher_id', name='uq_eval_c2_ref_teacher'),
    )
    op.create_index('idx_eval_c2_teacher', 'teacher_eval_finetune_performance', ['teacher_id', 'display_order'])


def downgrade() -> None:
    op.drop_index('idx_eval_c2_teacher', table_name='teacher_eval_finetune_performance')
    op.drop_table('teacher_eval_finetune_performance')
    op.drop_index('idx_eval_c1_teacher', table_name='teacher_eval_finetune_mastery')
    op.drop_table('teacher_eval_finetune_mastery')
    op.drop_index('idx_eval_b_teacher', table_name='teacher_eval_course62_polarity')
    op.drop_table('teacher_eval_course62_polarity')
    op.drop_index('idx_eval_a_teacher', table_name='teacher_eval_course62_mastery')
    op.drop_table('teacher_eval_course62_mastery')
