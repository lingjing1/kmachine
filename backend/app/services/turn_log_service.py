"""
Turn Log Service

記錄學生端 Chatbot 的完整回合資訊到 student_chatbot_turn_logs 表。
每個回合（turn）= 學生問一次 + AI 答一次 = 一筆記錄。

設計原則：
- 非阻塞：寫入失敗不影響主流程，只 log error
- 成本分開：embedding / LLM 各自計算
- 研究友好：記錄完整 prompt、精熟度快照、RAG 來源等
"""
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import Table, insert, text
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine, metadata

logger = logging.getLogger(__name__)

# Lazy loading for table
_turn_logs_table = None


def get_turn_logs_table() -> Table:
    global _turn_logs_table
    if _turn_logs_table is None:
        _turn_logs_table = Table('student_chatbot_turn_logs', metadata, autoload_with=engine)
    return _turn_logs_table


# ---- Cost Calculation ----

# OpenAI 官方定價 (2024/2025)
_PRICING = {
    "text-embedding-3-small": {
        "input": 0.020 / 1_000_000,   # $0.020 per 1M tokens
    },
    "gpt-4o-mini": {
        "input":  0.150 / 1_000_000,  # $0.150 per 1M tokens
        "output": 0.600 / 1_000_000,  # $0.600 per 1M tokens
    },
}


def calculate_embedding_cost(tokens: int) -> float:
    """計算 embedding API 的成本 (USD)"""
    price = _PRICING["text-embedding-3-small"]
    return tokens * price["input"]


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "gpt-4o-mini",
) -> float:
    """計算 LLM API 的成本 (USD)"""
    price = _PRICING.get(model)
    if not price:
        return 0.0
    return prompt_tokens * price["input"] + completion_tokens * price["output"]


# ---- Main Logging Function ----

def log_turn(
    # 關聯
    conversation_id: str,
    student_id: int,
    course_id: int,
    unit_id: Optional[int],
    user_message_id: int,
    ai_message_id: int,
    # 輸入/輸出
    user_query: str,
    ai_response: Optional[str] = None,
    full_prompt: Optional[str] = None,
    scaffolding_strategy: Optional[str] = None,
    # 精熟度快照
    mastery_snapshot: Optional[List[Dict]] = None,
    weak_points: Optional[List[str]] = None,
    # RAG 資訊
    rag_candidates_count: int = 0,
    rag_top_results: Optional[List[Dict]] = None,
    rag_cited_chunk_ids: Optional[List[int]] = None,
    # Token 用量（已拆分）
    embedding_tokens: int = 0,
    llm_prompt_tokens: int = 0,
    llm_completion_tokens: int = 0,
    # 延遲明細
    agent_timings: Optional[Dict[str, int]] = None,
    total_latency_ms: Optional[int] = None,
    # 上下文統計
    dialog_history_length: int = 0,
    related_dialogs_count: int = 0,
    unit_session_id: Optional[Any] = None,
    # 環境影響
    environmental_impact: Optional[Dict] = None,
    # 模型資訊
    model_name: Optional[str] = None,
) -> Optional[int]:
    """
    記錄一個完整回合的資訊。

    Returns:
        turn log record ID, or None if failed
    """
    try:
        # 計算成本
        embedding_cost = calculate_embedding_cost(embedding_tokens)
        llm_cost = calculate_llm_cost(llm_prompt_tokens, llm_completion_tokens)
        total_cost = embedding_cost + llm_cost

        timings = agent_timings or {}

        turn_logs_table = get_turn_logs_table()

        stmt = insert(turn_logs_table).values(
            conversation_id=conversation_id,
            student_id=student_id,
            course_id=course_id,
            unit_id=unit_id,
            user_message_id=user_message_id,
            ai_message_id=ai_message_id,

            user_query=user_query,
            full_prompt=full_prompt,
            ai_response=ai_response,
            scaffolding_strategy=scaffolding_strategy,

            mastery_snapshot=mastery_snapshot,
            weak_points=weak_points,

            rag_candidates_count=rag_candidates_count,
            rag_top_results=rag_top_results,
            rag_cited_chunk_ids=rag_cited_chunk_ids,

            embedding_tokens=embedding_tokens,
            llm_prompt_tokens=llm_prompt_tokens,
            llm_completion_tokens=llm_completion_tokens,
            embedding_cost_usd=embedding_cost,
            llm_cost_usd=llm_cost,
            total_cost_usd=total_cost,

            dialog_agent_ms=timings.get("dialog_agent_ms"),
            mastery_agent_ms=timings.get("mastery_agent_ms"),
            retrieval_agent_ms=timings.get("retrieval_agent_ms"),
            scaffolding_agent_ms=timings.get("scaffolding_agent_ms"),
            total_latency_ms=total_latency_ms,

            dialog_history_length=dialog_history_length,
            related_dialogs_count=related_dialogs_count,
            unit_session_id=unit_session_id,
            environmental_impact=environmental_impact,
            model_name=model_name,

            created_at=get_now_taipei(),
        ).returning(turn_logs_table.c.id)

        with engine.begin() as conn:
            result = conn.execute(stmt)
            turn_id = result.scalar_one()

        logger.info(
            f"Turn log #{turn_id} saved: "
            f"emb={embedding_tokens}tok llm={llm_prompt_tokens}+{llm_completion_tokens}tok "
            f"cost=${total_cost:.6f} latency={total_latency_ms}ms"
        )
        return turn_id

    except Exception as e:
        logger.error(f"Failed to log turn: {e}")
        return None
