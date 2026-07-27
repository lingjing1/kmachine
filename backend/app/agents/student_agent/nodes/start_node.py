"""
Start Node

職責：
1. 驗證必要欄位（Fail Fast 策略）
2. 初始化執行 Metadata（run_id, started_at）
3. 清空可能殘留的欄位（避免上次執行的資料污染）

輸入（從 State 讀取）：
- student_id: 學生 ID（必填）
- course_id: 課程 ID（必填）
- conversation_id: 對話 ID（必填）
- user_query: 使用者問題（必填）
- unit_id: 單元 ID（可選）
- knowledge_point_id: 知識點 ID（可選）
- job_id: 任務 ID（可選，用於 logging）

輸出（更新 State）：
- metadata: 執行 Metadata
- 清空的 Agent 輸出欄位（確保乾淨的初始狀態）
- error: 若驗證失敗則包含結構化錯誤物件
"""

from typing import Dict
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei
import uuid
from backend.app.agents.student_agent.state import StudentAgentState


def create_error(code: str, message: str, details: Dict = None) -> Dict:
    """建立結構化錯誤物件
    
    統一的錯誤格式，供所有 Agent Node 使用。
    
    Args:
        code: 錯誤代碼（如 MISSING_REQUIRED_FIELDS）
        message: 人類可讀的錯誤訊息
        details: 額外的錯誤細節（可選）
        
    Returns:
        Dict: 包含 code, message, details, timestamp 的錯誤物件
    """
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "timestamp": get_now_taipei().isoformat()
    }


def start_node(state: StudentAgentState) -> Dict:
    """
    Start Node - 初始化與驗證
    
    此節點是 Agent Graph 的入口點，負責：
    1. 驗證必要欄位是否存在（Fail Fast）
    2. 初始化執行 Metadata
    3. 清空可能殘留的欄位
    
    Args:
        state: Agent State，包含使用者輸入
        
    Returns:
        Dict: 更新的 state
              - 若驗證成功：包含清空後的初始狀態
              - 若驗證失敗：包含結構化的 error 物件
    """
    
    # 步驟 1：驗證必要欄位（Fail Fast）
    required_fields = {
        "student_id": "學生 ID",
        "course_id": "課程 ID",
        "conversation_id": "對話 ID",
        "user_query": "使用者問題"
    }
    
    missing_fields = []
    for field, label in required_fields.items():
        if not state.get(field):
            missing_fields.append(label)
    
    if missing_fields:
        return {
            "error": create_error(
                code="MISSING_REQUIRED_FIELDS",
                message=f"缺少必要欄位: {', '.join(missing_fields)}",
                details={
                    "missing_fields": missing_fields,
                    "received_state_keys": list(state.keys())
                }
            )
        }
    
    # 步驟 2：初始化 Metadata
    metadata = {
        "run_id": uuid.uuid4().hex,
        "started_at": get_now_taipei().isoformat(),
        "student_id": state["student_id"],
        "conversation_id": state["conversation_id"]
    }
    
    # 步驟 3：建立乾淨的初始狀態
    # 明確回傳所有欄位，避免依賴 LangGraph 的隱式 merge 行為
    clean_state = {
        # 輸入欄位（明確保留）
        "student_id": state["student_id"],
        "course_id": state["course_id"],
        "conversation_id": state["conversation_id"],
        "user_query": state["user_query"],
        "unit_id": state.get("unit_id"),
        "knowledge_point_id": state.get("knowledge_point_id"),
        "attachment_id": state.get("attachment_id"),
        "content_id": state.get("content_id"),
        "job_id": state.get("job_id"),
        
        # Metadata
        "metadata": metadata,
        
        # 清空所有 Agent 輸出欄位（避免上次執行的資料污染）
        "recent_dialogs": [],
        "related_dialogs": [],
        "condensed_history": "",
        "current_mastery": [],
        "weak_points": [],
        "retrieved_chunks": [],
        "chunk_sources": [],
        "scaffolding_strategy": None,
        "final_response": None,
        "sources": [],
        "error": None,
        
        # Turn log data
        "agent_timings": {},
        "full_prompt": None,
        "rag_candidates_count": 0,
    }
    
    return clean_state
