"""refactor_agent_logging_and_cleanup

Revision ID: 9e0b96485a79
Revises: 8387cbbf40d0
Create Date: 2026-02-13 11:40:24.699606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9e0b96485a79'
down_revision: Union[str, Sequence[str], None] = '8387cbbf40d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Refactor agent logging tables and cleanup unused tables."""
    # --- 1. orchestration_jobs 重構 ---
    # 變更為 JSONB (如果原本是 JSON) 並新增欄位
    op.add_column('orchestration_jobs', sa.Column('total_cost_usd', sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column('orchestration_jobs', sa.Column('total_cost_twd', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('orchestration_jobs', sa.Column('used_models', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # 修改原本的 job_context 改名為 input_config
    # 注意：這裡使用 alter_column 如果有舊名則改名。根據之前檢查，應為 job_context
    op.alter_column('orchestration_jobs', 'job_context', new_column_name='input_config')

    # 補上：把型別從 json 真的轉成 jsonb，才能用 || 和 jsonb_build_object
    op.execute("ALTER TABLE orchestration_jobs ALTER COLUMN input_config TYPE jsonb USING input_config::jsonb")

    # 數據移轉：將 input_prompt, workflow_type, experiment_config 合併入 input_config
    # 使用 jsonb_build_object 確保結構化
    op.execute("""
        UPDATE orchestration_jobs 
        SET input_config = COALESCE(input_config, '{}'::jsonb) || 
            jsonb_build_object(
                'original_prompt', input_prompt,
                'workflow_type', workflow_type,
                'experiment_config', experiment_config
            )
    """)

    # 刪除已整併的冗餘欄位
    op.drop_column('orchestration_jobs', 'input_prompt')
    op.drop_column('orchestration_jobs', 'workflow_type')
    op.drop_column('orchestration_jobs', 'experiment_config')

    # --- 2. agent_tasks 重構 ---
    op.drop_column('agent_tasks', 'task_description')

    # --- 3. agent_task_sources 重構與去重 ---
    op.add_column('agent_task_sources', sa.Column('job_id', sa.Integer(), nullable=True))
    
    # 補齊 job_id (從 agent_tasks 關聯)
    op.execute("""
        UPDATE agent_task_sources ATS
        SET job_id = AT.job_id
        FROM agent_tasks AT
        WHERE ATS.task_id = AT.id
    """)
    
    # 資料清理：刪除同一個 Job 內重複的來源，只保留第一個 Task 的紀錄
    op.execute("""
        DELETE FROM agent_task_sources
        WHERE (task_id, source_id, source_type) IN (
            SELECT task_id, source_id, source_type
            FROM (
                SELECT 
                    ATS.task_id, ATS.source_id, ATS.source_type,
                    ROW_NUMBER() OVER (PARTITION BY AT.job_id, ATS.source_id, ATS.source_type ORDER BY ATS.task_id) as rn
                FROM agent_task_sources ATS
                JOIN agent_tasks AT ON ATS.task_id = AT.id
            ) t
            WHERE rn > 1
        )
    """)
    
    # 設定 job_id 為必填 (非必要可選)
    # op.alter_column('agent_task_sources', 'job_id', nullable=False)
    
    # 建立唯一性約束 (預防未來重複錄入)
    op.create_unique_constraint('uq_job_source_dedup', 'agent_task_sources', ['job_id', 'source_id', 'source_type'])

    # --- 4. 刪除棄用表 ---
    op.execute("DROP TABLE IF EXISTS knowledge_point_contents CASCADE")
    op.execute("DROP TABLE IF EXISTS material_knowledge_points CASCADE")
    op.execute("DROP TABLE IF EXISTS orchestration_job_sources CASCADE")
    op.execute("DROP TABLE IF EXISTS content_question CASCADE")


def downgrade() -> None:
    """Downgrade schema (Partial - recommended to use backup for this kind of refactor)."""
    # 由於包含大量的刪除欄位與表，強烈建議在執行前備份資料庫。
    pass
