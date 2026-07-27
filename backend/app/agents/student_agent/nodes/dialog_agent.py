"""
Dialog Agent Node

職責：
1. 取得當前對話的最近 N 筆記錄（結構化資料）
2. 使用向量搜尋跨對話相關歷史（語意搜尋）
3. 將對話歷史壓縮為字串格式（智慧壓縮策略）

輸入（從 State 讀取）：
- student_id: 學生 ID
- conversation_id: 對話 ID
- user_query: 使用者問題

輸出（更新 State）：
- recent_dialogs: 當前對話的最近記錄
- related_dialogs: 跨對話相關記錄
- condensed_history: 壓縮後的對話歷史字串

輔助函式（供 Router 使用）：
- save_dialog_message(): 儲存對話訊息到資料庫（含 Embedding）
- condense_dialog_history(): 智慧壓縮對話歷史
  * 學生問題：100% 完整保留
  * AI 回應：截斷至前 150 字元（在句號處斷開）
  * 最近一輪 AI 回應：完整保留（可能與追問相關）
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy import Table, select, insert, text
from backend.app.agents.student_agent.state import StudentAgentState
from backend.app.agents.student_agent.nodes.start_node import create_error
from backend.app.utils.db_logger import engine, metadata
from backend.app.utils.time_utils import get_now_taipei
import os
from openai import OpenAI

# === OpenAI 客戶端設定 ===
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=10.0,   # 請求超時 10 秒
    max_retries=1   # 最多重試 1 次
)

EMBEDDING_MODEL = os.getenv("STUDENT_CHATBOT_EMBEDDING_MODEL", "text-embedding-3-small")


def get_embedding(text: str) -> Dict[str, Any]:
    """生成文字的 Embedding 向量並回傳 Token 使用量
    
    使用 OpenAI text-embedding-3-small 模型生成 1536 維向量。
    
    Returns:
        Dict: {"embedding": List[float], "usage": int}
    """
    if not text or not text.strip():
        return {"embedding": None, "usage": 0}
    try:
        response = openai_client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        return {
            "embedding": response.data[0].embedding,
            "usage": response.usage.prompt_tokens
        }
    except Exception as e:
        print(f"生成 Embedding 時發生錯誤: {e}")
        return {"embedding": None, "usage": 0}


def _to_pgvector_str(vec: List[float]) -> str:
    """將 Python 向量轉換為 pgvector 格式字串
    
    pgvector 需要 '[x1,x2,x3,...]' 格式的字串。
    """
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


# === 資料庫表格反射（Lazy Loading）===
_dialog_table_cache = None

def get_dialog_table() -> Table:
    """延遲載入對話表格
    
    避免在 import 時就連接資料庫，提升啟動速度和測試靈活性。
    """
    global _dialog_table_cache
    if _dialog_table_cache is None:
        _dialog_table_cache = Table('student_chatbot_dialogs', metadata, autoload_with=engine)
    return _dialog_table_cache


# === 儲存功能（供 Router 使用）===

def save_dialog_message(
    student_id: int,
    course_id: int,
    conversation_id: str,
    role: str,
    content: Dict[str, Any],
    unit_id: Optional[int] = None,
    knowledge_point_id: Optional[int] = None,
    attachment_id: Optional[int] = None,
    content_id: Optional[int] = None,
    unit_session_id: Optional[Any] = None
) -> (int, int):
    """儲存對話訊息到資料庫並回傳 ID 與 Token 使用量"""
    # 步驟 1：生成 Embedding
    message_text = content.get("message", "")
    embed_res = get_embedding(message_text)
    embedding = embed_res["embedding"]
    tokens = embed_res["usage"]
    
    # 步驟 2：寫入資料庫（使用自動交易管理）
    student_chatbot_dialogs = get_dialog_table()
    
    with engine.begin() as conn:
        stmt = insert(student_chatbot_dialogs).values(
            student_id=student_id,
            course_id=course_id,
            unit_id=unit_id,
            knowledge_point_id=knowledge_point_id,
            attachment_id=attachment_id,
            content_id=content_id,
            unit_session_id=unit_session_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            content_embedding=embedding,
            created_at=get_now_taipei()
        ).returning(student_chatbot_dialogs.c.id)
        
        result = conn.execute(stmt)
        msg_id = result.scalar_one()
        
    return msg_id, tokens


# === 檢索功能 ===

def get_recent_dialogs(student_id: int, conversation_id: str, limit: int = 10) -> List[Dict]:
    """取得當前對話的最近 N 筆記錄
    
    Args:
        student_id: 學生 ID
        conversation_id: 對話 ID
        limit: 最多返回筆數（預設 10）
        
    Returns:
        List[Dict]: 按時間順序排列的對話記錄（從舊到新）
    """
    student_chatbot_dialogs = get_dialog_table()
    
    with engine.connect() as conn:
        stmt = select(
            student_chatbot_dialogs.c.role,
            student_chatbot_dialogs.c.content,
            student_chatbot_dialogs.c.created_at
        ).where(
            student_chatbot_dialogs.c.student_id == student_id,
            student_chatbot_dialogs.c.conversation_id == conversation_id
        ).order_by(
            student_chatbot_dialogs.c.created_at.desc()
        ).limit(limit)
        
        results = conn.execute(stmt).fetchall()
        
        # 反轉為時間順序（從舊到新）
        return [
            {"role": row.role, "content": row.content, "created_at": row.created_at}
            for row in reversed(results)
        ]


def vector_search_related_dialogs(
    student_id: int, 
    query_text: str, 
    exclude_conversation_id: str,
    course_id: int = None,
    limit: int = 3,
    similarity_threshold: float = 0.3
) -> (List[Dict], int):
    """跨對話搜尋學生相關提問（只搜 role='user'）"""
    embed_res = get_embedding(query_text)
    query_embedding = embed_res["embedding"]
    tokens = embed_res["usage"]

    if not query_embedding:
        return [], tokens
    
    with engine.connect() as conn:
        sql = """
            SELECT role, content, conversation_id, unit_id, knowledge_point_id,
                   GREATEST(0.0, 1 - (content_embedding <=> (:embedding)::vector)) as similarity
            FROM student_chatbot_dialogs
            WHERE student_id = :student_id
              AND conversation_id != :exclude_conversation_id
              AND content_embedding IS NOT NULL
              AND role = 'user'
              AND (:course_id IS NULL OR course_id = :course_id)
            ORDER BY content_embedding <=> (:embedding)::vector
            LIMIT :limit
        """
        
        results = conn.execute(text(sql), {
            "student_id": student_id,
            "exclude_conversation_id": exclude_conversation_id,
            "embedding": _to_pgvector_str(query_embedding),
            "limit": int(limit),
            "course_id": course_id
        }).fetchall()
        
        # 過濾低相似度結果
        items = [
            {
                "role": row.role,
                "content": row.content,
                "conversation_id": row.conversation_id,
                "similarity": row.similarity
            }
            for row in results
            if row.similarity >= similarity_threshold
        ]
        return items, tokens


def condense_dialog_history(dialogs: List[Dict], max_ai_chars: int = 150, exclude_last_user: bool = True) -> str:
    """將對話記錄壓縮為字串格式（智慧壓縮策略）
    
    壓縮策略：
    - 學生問題：100% 完整保留
    - AI 回應：截斷至前 max_ai_chars 字元（到句號處）
    - 最近一輪 AI 回應：完整保留（可能與追問相關）
    
    Args:
        dialogs: 對話記錄列表
        max_ai_chars: AI 回應的最大字元數（預設 150）
        exclude_last_user: 是否排除最後一筆使用者訊息（預設 True，因為 user_query 已單獨顯示）
        
    Returns:
        str: 壓縮後的對話歷史字串
    """
    # 角色名稱對應（避免 prompt 混亂）
    role_map = {
        "user": "Student",
        "assistant": "AI",
        "system": "System",
        "tutor": "AI"
    }
    
    # 排除最後一筆使用者訊息（當前 query）
    if exclude_last_user and dialogs and dialogs[-1]["role"] == "user":
        dialogs = dialogs[:-1]
    
    # 如果排除後沒有對話，返回空
    if not dialogs:
        return ""
    
    lines = []
    total = len(dialogs)
    
    for i, d in enumerate(dialogs):
        who = role_map.get(d["role"], d["role"])
        msg = d["content"].get("message", "")
        
        # 學生問題：完整保留
        if d["role"] == "user":
            lines.append(f"{who}: {msg}")
        
        # AI 回應：處理截斷
        elif d["role"] == "assistant":
            # 判斷是否為最後一筆 AI 回應（完整保留）
            is_last_ai = (i == total - 1) or (i == total - 2 and dialogs[-1]["role"] == "user")
            
            if is_last_ai or len(msg) <= max_ai_chars:
                lines.append(f"{who}: {msg}")
            else:
                # 截斷到句號處，避免句子斷在中間
                truncated = msg[:max_ai_chars]
                # 嘗試在句號處斷開
                if '。' in truncated:
                    truncated = truncated.rsplit('。', 1)[0] + '。'
                elif '.' in truncated:
                    truncated = truncated.rsplit('.', 1)[0] + '.'
                lines.append(f"{who}: {truncated}...")
    
    return "\n".join(lines)


# === Node 定義 ===


def dialog_agent_node(state: StudentAgentState) -> Dict:
    """
    Dialog Agent 節點 (Student Side)
    
    職責：
    1. 取得當前對話的最近記錄（結構化資料）
    2. 使用向量搜尋跨對話相關歷史（語意搜尋）
    3. 將對話歷史壓縮為字串格式
    
    輸入（從 State 讀取）：
    - user_query: 使用者問題
    - student_id: 學生 ID
    - conversation_id: 對話 ID
    
    輸出（更新 State）：
    - recent_dialogs: 當前對話的最近記錄
    - related_dialogs: 跨對話相關記錄
    - condensed_history: 壓縮後的對話歷史字串
    """
    try:
        student_id = state["student_id"]
        conversation_id = state["conversation_id"]
        user_query = state["user_query"]
        
        # 步驟 1：取得當前對話的最近記錄
        recent = get_recent_dialogs(student_id, conversation_id, limit=10)
        
        # Fix: Convert datetime objects to ISO strings for JSON serialization
        for r in recent:
            if isinstance(r.get("created_at"), datetime):
                r["created_at"] = r["created_at"].isoformat()
        
        # 步驟 2：跨對話向量搜尋（只搜學生提問，最多 3 筆）
        related = []
        embedding_usage = 0
        if len(user_query) > 2:
            related, embedding_usage = vector_search_related_dialogs(
                student_id, 
                user_query, 
                conversation_id,
                course_id=state.get("course_id"),
                limit=3,
                similarity_threshold=0.3
            )
        
        # 步驟 2b：壓縮 related_dialogs 的訊息內容（截斷至 150 字）
        for rd in related:
            content = rd.get("content", {})
            if isinstance(content, dict):
                msg = content.get("message", "")
                if len(msg) > 150:
                    truncated = msg[:150]
                    if '。' in truncated:
                        truncated = truncated.rsplit('。', 1)[0] + '。'
                    elif '.' in truncated:
                        truncated = truncated.rsplit('.', 1)[0] + '.'
                    content["message"] = truncated + "..."
        
        # 步驟 3：壓縮對話歷史
        condensed = condense_dialog_history(recent)
        
        return {
            "recent_dialogs": recent,
            "related_dialogs": related,
            "condensed_history": condensed,
            "usage": {
                "prompt_tokens": embedding_usage,
                "completion_tokens": 0,
                "total_tokens": embedding_usage
            }
        }
        
    except Exception as e:
        return {
            "error": create_error(
                code="DIALOG_RETRIEVAL_ERROR",
                message="對話檢索失敗",
                details={"exception": str(e)}
            )
        }
