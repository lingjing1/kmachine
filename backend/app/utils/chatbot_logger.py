
"""
Student Chatbot Logger
用於記錄學生端 Chatbot 的效能 Metrics (Tokens, Latency, Cost) 到 student_chatbot_metrics 表。
獨立於 db_logger (agent_tasks) 以避免與教師端邏輯混用。
"""
import logging
from datetime import datetime
from sqlalchemy import insert
from backend.app.db import engine, metadata
from backend.app.utils.time_utils import get_now_taipei
from sqlalchemy import Table

# 設定 Logger
logger = logging.getLogger(__name__)

# Lazy loading for table
_chatbot_metrics_table = None

def get_chatbot_metrics_table() -> Table:
    global _chatbot_metrics_table
    if _chatbot_metrics_table is None:
        _chatbot_metrics_table = Table('student_chatbot_metrics', metadata, autoload_with=engine)
    return _chatbot_metrics_table

def calculate_llm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    計算 LLM 使用成本 (USD)
    目前以 gpt-4o-mini 為主:
    - Input: $0.150 / 1M tokens
    - Output: $0.600 / 1M tokens
    """
    if "gpt-4o-mini" in model_name:
        input_cost = (prompt_tokens / 1_000_000) * 0.150
        output_cost = (completion_tokens / 1_000_000) * 0.600
        return input_cost + output_cost
    
    # 預設：若不認識模型，則返回 0 或給一個保守估計
    return 0.0

def log_chatbot_metric(
    dialog_id: int,
    conversation_id: str,
    latency_ms: int,
    model_name: str = "gpt-4o-mini",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float = 0.0
):
    """
    記錄 Chatbot 對話的效能 Metrics
    """
    try:
        metrics_table = get_chatbot_metrics_table()
        
        # 計算總 Tokens
        total_tokens = prompt_tokens + completion_tokens
        
        # 如果沒有傳入成本，則自動計算
        if estimated_cost_usd == 0.0 and total_tokens > 0:
            estimated_cost_usd = calculate_llm_cost(model_name, prompt_tokens, completion_tokens)
        
        stmt = insert(metrics_table).values(
            dialog_id=dialog_id,
            conversation_id=conversation_id,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost_usd,
            created_at=get_now_taipei()
        )
        
        with engine.begin() as conn:
            conn.execute(stmt)
            
        logger.info(f"Logged accurate metrics for dialog {dialog_id}: {total_tokens} tokens, {latency_ms}ms, ${estimated_cost_usd:.6f}")
        
    except Exception as e:
        logger.error(f"Failed to log chatbot metrics for dialog {dialog_id}: {e}")

