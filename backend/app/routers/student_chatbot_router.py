"""
Student Chatbot Router: 處理學生對話機器人相關功能
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import Table, select, insert, update, delete, and_, or_, desc, func, text
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.utils.db_logger import engine, metadata
from backend.app.utils import db_logger, chatbot_logger
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.time_utils import get_now_taipei
import uuid

# 建立 Router
router = APIRouter(prefix="/api/v1/student/chatbot", tags=["Student Chatbot"])

# 反射資料表
try:
    student_chatbot_dialogs = Table('student_chatbot_dialogs', metadata, autoload_with=engine)
    student_knowledge_mastery = Table('student_knowledge_mastery', metadata, autoload_with=engine)
    users_table = Table('users', metadata, autoload_with=engine)
    course_units = Table('course_units', metadata, autoload_with=engine)
    knowledge_points = Table('knowledge_points', metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting student chatbot tables: {e}")

# ==================== Pydantic Schemas ====================

class SendMessageRequest(BaseModel):
    """發送訊息請求"""
    conversation_id: Optional[str] = Field(None, description="對話 ID（若未提供則創建新對話）")
    message: str = Field(..., min_length=1, description="學生訊息內容")
    course_id: int = Field(..., description="課程 ID")
    unit_id: Optional[int] = Field(None, description="章節 ID（可選）")
    knowledge_point_id: Optional[int] = Field(None, description="知識點 ID（可選）")
    attachment_id: Optional[int] = Field(None, description="附件 ID（在 AttachmentViewer 閱讀附件時傳入）")
    content_id: Optional[int] = Field(None, description="教材 ID（在 Topic Preview 閱讀預習/複習教材時傳入）")
    student_id: Optional[int] = Field(None, description="學生 ID（測試用，未來由 JWT 提供）")
    unit_session_id: Optional[uuid.UUID] = Field(None, description="預習/複習階段的 Session ID")


class SourceItem(BaseModel):
    """來源引用項目"""
    chunk_id: int
    title: Optional[str] = Field(None, description="知識點名稱")
    section: Optional[str] = Field(None, description="單元名稱")
    snippet: Optional[str] = Field(None, description="內容摘錄")
    page_numbers: Optional[str] = Field(None, description="頁碼")
    source_filename: Optional[str] = Field(None, description="來源檔案")
    locator: Optional[str] = Field(None, description="定位資訊 (單元 | 頁碼)")


class SendMessageResponse(BaseModel):
    """發送訊息回應"""
    conversation_id: str
    user_message_id: int
    assistant_message_id: int
    assistant_response: str
    sources: Optional[List[SourceItem]] = Field(None, description="引用來源列表")
    metadata: Optional[Dict[str, Any]] = None


class DialogMessage(BaseModel):
    """對話訊息"""
    id: int
    role: str
    content: Dict[str, Any]
    created_at: datetime


class GetConversationHistoryResponse(BaseModel):
    """獲取對話歷史回應"""
    conversation_id: str
    messages: List[DialogMessage]
    total_count: int


class ConversationSummary(BaseModel):
    """對話摘要"""
    conversation_id: str
    first_message: str
    last_message_at: datetime
    message_count: int
    unit_id: Optional[int] = None
    knowledge_point_id: Optional[int] = None


class GetConversationsResponse(BaseModel):
    """獲取對話列表回應"""
    conversations: List[ConversationSummary]
    total_count: int


class DeleteConversationResponse(BaseModel):
    """刪除對話回應"""
    success: bool
    deleted_count: int


class KnowledgeMasteryItem(BaseModel):
    """知識點精熟度項目"""
    unit_id: int
    knowledge_point_id: int
    knowledge_point_name: Optional[str] = None
    mastery_level: str
    preview_completed: bool
    review_completed: bool
    last_assessed_at: Optional[datetime] = None


class GetKnowledgeMasteryResponse(BaseModel):
    """獲取知識點精熟度回應"""
    mastery_items: List[KnowledgeMasteryItem]
    total_count: int


# ==================== Helper Functions ====================

# ✅ Phase 3: get_current_user_id 已從 auth_utils 導入，移除本地實作


def create_user_message_content(message: str) -> Dict[str, Any]:
    """建立使用者訊息內容（JSON 格式）"""
    return {
        "type": "text",
        "message": message,
        "timestamp": get_now_taipei().isoformat()
    }


def create_assistant_message_content(
    message: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    mastery_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """建立 AI 助理訊息內容（JSON 格式）"""
    content = {
        "type": "text",
        "message": message,
        "timestamp": get_now_taipei().isoformat()
    }
    
    if sources:
        content["sources"] = sources
    
    if mastery_context:
        content["mastery_context"] = mastery_context
    
    return content


def validate_course_hierarchy(
    course_id: int,
    unit_id: Optional[int] = None,
    knowledge_point_id: Optional[int] = None
) -> None:
    """
    驗證課程階層的資料一致性
    
    確保：
    1. unit_id 確實屬於指定的 course_id
    2. knowledge_point_id 確實屬於指定的 unit_id 和 course_id
    
    如果驗證失敗，拋出 HTTPException
    """
    with engine.connect() as conn:
        # 驗證 unit_id 是否屬於 course_id
        if unit_id is not None:
            unit_query = select(course_units.c.id).where(
                and_(
                    course_units.c.id == unit_id,
                    course_units.c.course_id == course_id
                )
            )
            unit_result = conn.execute(unit_query).fetchone()
            
            if not unit_result:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unit ID {unit_id} 不屬於 Course ID {course_id}"
                )
        
        # 驗證 knowledge_point_id 是否屬於 unit_id（如果兩者都提供）
        if knowledge_point_id is not None:
            if unit_id is None:
                # 如果只提供 knowledge_point_id 但沒有 unit_id，
                # 至少要驗證它屬於該 course
                kp_query = select(knowledge_points.c.id).where(
                    and_(
                        knowledge_points.c.id == knowledge_point_id,
                        knowledge_points.c.course_id == course_id
                    )
                )
            else:
                # 如果兩者都提供，驗證 knowledge_point 屬於 unit
                kp_query = select(knowledge_points.c.id).where(
                    and_(
                        knowledge_points.c.id == knowledge_point_id,
                        knowledge_points.c.unit_id == unit_id,
                        knowledge_points.c.course_id == course_id
                    )
                )
            
            kp_result = conn.execute(kp_query).fetchone()
            
            if not kp_result:
                if unit_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Knowledge Point ID {knowledge_point_id} 不屬於 Unit ID {unit_id}"
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Knowledge Point ID {knowledge_point_id} 不屬於 Course ID {course_id}"
                    )



def _sync_get_last_mastery_context(conversation_id: str):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT content 
            FROM student_chatbot_dialogs 
            WHERE conversation_id = :conv_id AND role = 'assistant'
            ORDER BY created_at DESC 
            LIMIT 1
        """), {"conv_id": conversation_id}).fetchone()
        return result


def update_dialog_kp(dialog_id: int, kp_id: int):
    """更新對話記錄的知識點 ID"""
    with engine.begin() as conn:
        conn.execute(
            update(student_chatbot_dialogs)
            .where(student_chatbot_dialogs.c.id == dialog_id)
            .values(knowledge_point_id=kp_id)
        )

# ==================== API Endpoints ====================

# Import Student Agent Logic
from backend.app.agents.student_agent.nodes.dialog_agent import save_dialog_message
from backend.app.agents.student_agent.graph import student_agent_app

@router.post("/messages", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    發送訊息給 chatbot
    
    流程：
    1. 驗證資料階層一致性
    2. 若未提供 conversation_id，創建新對話
    3. 儲存使用者訊息（含向量 Embedding）
    4. 呼叫 LangGraph Agent 生成回應
    5. 儲存 AI 回應（含向量 Embedding）
    6. 返回結果
    """
    student_id = request.student_id or current_user_id
    
    # 1. 驗證資料階層一致性
    await run_in_db_pool(
        validate_course_hierarchy,
        course_id=request.course_id,
        unit_id=request.unit_id,
        knowledge_point_id=request.knowledge_point_id
    )
    
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    
    # 2. 儲存使用者訊息 (使用 Dialog Agent 的 helper function，支援向量)
    user_content = create_user_message_content(request.message)
    user_message_id, user_msg_tokens = await run_in_db_pool(
        save_dialog_message,
        student_id=student_id,
        course_id=request.course_id,
        conversation_id=conversation_id,
        role="user",
        content=user_content,
        unit_id=request.unit_id,
        knowledge_point_id=request.knowledge_point_id,
        attachment_id=request.attachment_id,
        content_id=request.content_id,
        unit_session_id=request.unit_session_id
    )
    

    # 3. Create Job (Student Chatbot NO LONGER uses db_logger/orchestration_jobs)
    # job_id = await run_in_db_pool(...) -> REMOVED
    job_id = 0 # Placeholder if needed by graph, but we'll try to remove dependency
    
    # 4. 檢查精熟度快取（優先使用應用層快取，完全不碰 DB）
    from backend.app.utils.mastery_cache import get_mastery, set_mastery
    from sqlalchemy import text
    
    cached_mastery = None
    cached_weak_points = None
    
    # 先從應用層快取取得（完全不碰 DB）
    if conversation_id:
        cached = get_mastery(student_id, request.course_id, conversation_id)
        if cached:
            cached_mastery = cached.get("current_mastery")
            cached_weak_points = cached.get("weak_points")
    
    # 快取未命中 → 從 DB 補一次（僅對既有對話）
    if (cached_mastery is None and cached_weak_points is None) and request.conversation_id:
        result = await run_in_db_pool(_sync_get_last_mastery_context, request.conversation_id)
            
        if result and result.content and isinstance(result.content, dict):
                mastery_ctx = result.content.get("mastery_context", {})
                cached_mastery = mastery_ctx.get("current_mastery")
                cached_weak_points = mastery_ctx.get("weak_points")
                
                # 寫入應用層快取，下次不必再碰 DB
                if cached_mastery is not None or cached_weak_points is not None:
                    set_mastery(
                        student_id, request.course_id, conversation_id,
                        {"current_mastery": cached_mastery, "weak_points": cached_weak_points}
                    )
    
    # 5. 呼叫 Chatbot Agent (LangGraph)
    agent_inputs = {
        "student_id": student_id,
        "course_id": request.course_id,
        "conversation_id": conversation_id,
        "user_query": request.message,
        "unit_id": request.unit_id,
        "knowledge_point_id": request.knowledge_point_id,
        "attachment_id": request.attachment_id,
        "content_id": request.content_id,
        "job_id": job_id,
        # 傳遞快取的 mastery 資料（若有）
        "current_mastery": cached_mastery,
        "weak_points": cached_weak_points,
        # 初始化 Usage
        "usage": {
            "prompt_tokens": user_msg_tokens,
            "completion_tokens": 0,
            "total_tokens": user_msg_tokens
        }
    }
    
    import time
    start_time = time.perf_counter()
    error_info = None
    
    try:
        # 使用 ainvoke 非同步調用
        agent_result = await student_agent_app.ainvoke(agent_inputs)
        
        # 提取結果
        assistant_response_text = agent_result.get("final_response") or "系統發生錯誤，無法生成回應。"
        sources = agent_result.get("sources", [])
        scaffolding_strategy = agent_result.get("scaffolding_strategy")
        detected_kp_id = agent_result.get("detected_knowledge_point_id")
        
        if agent_result.get("error"):
            error_info = agent_result['error']
            print(f"Agent Error: {error_info}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error invoking agent: {e}")
        assistant_response_text = "系統繁忙中，請稍後再試。" 
        sources = []
        scaffolding_strategy = "error_fallback"
        error_info = str(e)
    
    end_time = time.perf_counter()
    latency_ms = int((end_time - start_time) * 1000)

    # 6. 儲存 AI 回應（包含 mastery 快取資訊）
    # 取得 mastery 資料（優先使用 agent 結果，否則使用快取）
    final_mastery = None
    final_weak_points = None
    if 'agent_result' in locals():
        # 使用 is not None 檢查，避免空 dict {} 被 `or` 誤判為 falsy
        agent_mastery = agent_result.get("current_mastery")
        agent_weak = agent_result.get("weak_points")
        final_mastery = agent_mastery if agent_mastery is not None else cached_mastery
        final_weak_points = agent_weak if agent_weak is not None else cached_weak_points
    else:
        final_mastery = cached_mastery
        final_weak_points = cached_weak_points
    
    # 寫入應用層快取（供後續訊息使用）
    if final_mastery is not None or final_weak_points is not None:
        set_mastery(
            student_id, request.course_id, conversation_id,
            {"current_mastery": final_mastery, "weak_points": final_weak_points}
        )
    
    assistant_content = create_assistant_message_content(
        message=assistant_response_text,
        sources=sources,
        mastery_context={
            "strategy": scaffolding_strategy,
            "error": str(error_info) if error_info else None,
            # 快取 mastery 資訊供下次使用
            "current_mastery": final_mastery,
            "weak_points": final_weak_points
        }
    )
    
    kp_to_save = request.knowledge_point_id or detected_kp_id
    
    assistant_message_id, assistant_msg_tokens = await run_in_db_pool(
        save_dialog_message,
        student_id=student_id,
        course_id=request.course_id,
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        unit_id=request.unit_id,
        knowledge_point_id=kp_to_save,
        attachment_id=request.attachment_id,
        content_id=request.content_id,
        unit_session_id=request.unit_session_id
    )

    # 6b. 若 AI 成功偵測到知識點且原本請求中沒有，回頭更新使用者訊息的 KP ID
    if detected_kp_id and not request.knowledge_point_id:
        await run_in_db_pool(
            update_dialog_kp,
            user_message_id,
            detected_kp_id
        )
    
    # 7. Log Metrics (Student Chatbot Logger — 保留既有 metrics)
    # Get accurate usage from agent and add assistant embedding tokens
    final_usage = agent_result.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}) if 'agent_result' in locals() else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = final_usage.get("prompt_tokens", 0)
    completion_tokens = final_usage.get("completion_tokens", 0) + assistant_msg_tokens # Assistant content embedding is part of completion flow
    
    await run_in_db_pool(
        chatbot_logger.log_chatbot_metric,
        dialog_id=assistant_message_id,
        conversation_id=conversation_id,
        latency_ms=latency_ms,
        model_name="gpt-4o-mini",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=0.0 # Will be auto-calculated by logger
    )
    
    # 7b. Turn Log（完整回合記錄 — 用於成本分析與研究）
    from backend.app.services.turn_log_service import log_turn
    import re as _re
    
    # 從 agent_result 提取 turn log 所需資料
    _agent_timings = agent_result.get("agent_timings", {}) if 'agent_result' in locals() else {}
    _full_prompt = agent_result.get("full_prompt") if 'agent_result' in locals() else None
    _rag_candidates_count = agent_result.get("rag_candidates_count", 0) if 'agent_result' in locals() else 0
    _mastery_snapshot = final_mastery if isinstance(final_mastery, list) else None
    _weak_points_list = list(final_weak_points) if isinstance(final_weak_points, list) else None
    
    # RAG top results（從 agent 的 chunk_sources）
    _rag_top_results = agent_result.get("chunk_sources", []) if 'agent_result' in locals() else []
    
    # 從 RAG 檢索到的 chunk IDs（記錄送入 prompt 的參考教材）
    _cited_ids = [s["chunk_id"] for s in _rag_top_results if s.get("chunk_id")] if _rag_top_results else []
    
    # Embedding tokens = user_msg_tokens + assistant_msg_tokens + dialog vector search tokens
    # LLM tokens = prompt_tokens - embedding tokens 部分, completion_tokens - assistant embedding
    _embedding_tokens = user_msg_tokens + assistant_msg_tokens
    _llm_prompt = final_usage.get("prompt_tokens", 0) - user_msg_tokens  # 扣除 user embedding
    _llm_completion = final_usage.get("completion_tokens", 0)
    
    # 對話歷史統計
    _recent = agent_result.get("recent_dialogs", []) if 'agent_result' in locals() else []
    _related = agent_result.get("related_dialogs", []) if 'agent_result' in locals() else []
    
    # 碳排資料
    _environmental_impact = agent_result.get("environmental_impact") if 'agent_result' in locals() else None
    
    await run_in_db_pool(
        log_turn,
        conversation_id=conversation_id,
        student_id=student_id,
        course_id=request.course_id,
        unit_id=request.unit_id,
        user_message_id=user_message_id,
        ai_message_id=assistant_message_id,
        user_query=request.message,
        ai_response=assistant_response_text,
        full_prompt=_full_prompt,
        scaffolding_strategy=scaffolding_strategy,
        mastery_snapshot=_mastery_snapshot,
        weak_points=_weak_points_list,
        rag_candidates_count=_rag_candidates_count,
        rag_top_results=_rag_top_results if _rag_top_results else None,
        rag_cited_chunk_ids=_cited_ids if _cited_ids else None,
        embedding_tokens=_embedding_tokens,
        llm_prompt_tokens=max(0, _llm_prompt),
        llm_completion_tokens=_llm_completion,
        agent_timings=_agent_timings,
        total_latency_ms=latency_ms,
        dialog_history_length=len(_recent),
        related_dialogs_count=len(_related),
        unit_session_id=request.unit_session_id,
        environmental_impact=_environmental_impact,
        model_name=agent_result.get("model_name") if 'agent_result' in locals() else None,
    )
    
    # 8. 返回結果
    return SendMessageResponse(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        assistant_response=assistant_response_text,
        sources=sources, # 傳遞完整來源資訊
        metadata={
            "scaffolding_strategy": scaffolding_strategy,
            "sources_count": len(sources),
            "sources_preview": [
                {
                    "chunk_id": s.get("chunk_id"),
                    "source_filename": s.get("source_filename"),
                    "original_score": s.get("original_score"),
                    "rerank_score": s.get("rerank_score")
                }
                for s in sources[:2] 
            ] if sources else [],
            "error": str(error_info) if error_info else None,
            "latency_ms": latency_ms
        }
    )


@router.get("/conversations", response_model=GetConversationsResponse)
async def get_conversations(
    course_id: int,
    unit_id: int,
    knowledge_point_id: Optional[int] = None,
    attachment_id: Optional[int] = None,
    content_id: Optional[int] = None,
    student_id: int = Depends(get_current_user_id)
):
    """
    獲取學生的對話列表
    
    查詢參數：
    - course_id: 課程 ID（必填）
    - unit_id: 章節 ID（必填）
    - knowledge_point_id: 知識點 ID（可選）
    - attachment_id: 附件 ID（可選，用於 AttachmentViewer 場景，避免同一知識點下不同附件的對話混在一起）
    - content_id: 教材內容 ID（可選，用於 TopicPreview 場景）
    """
    # student_id 已經由 Depends 注入
    
    with engine.connect() as conn:
        # 構建查詢條件（course_id 和 unit_id 必填）
        conditions = [
            student_chatbot_dialogs.c.student_id == student_id,
            student_chatbot_dialogs.c.course_id == course_id,
            student_chatbot_dialogs.c.unit_id == unit_id
        ]
        
        if knowledge_point_id:
            conditions.append(student_chatbot_dialogs.c.knowledge_point_id == knowledge_point_id)

        if attachment_id:
            conditions.append(student_chatbot_dialogs.c.attachment_id == attachment_id)

        if content_id:
            conditions.append(student_chatbot_dialogs.c.content_id == content_id)
            
        # 聚合查詢：按 conversation_id 分組
        query = select(
            student_chatbot_dialogs.c.conversation_id,
            func.min(student_chatbot_dialogs.c.content['message'].astext).label('first_message'),
            func.max(student_chatbot_dialogs.c.created_at).label('last_message_at'),
            func.count(student_chatbot_dialogs.c.id).label('message_count'),
            student_chatbot_dialogs.c.unit_id,
            student_chatbot_dialogs.c.knowledge_point_id
        ).where(
            and_(*conditions)
        ).group_by(
            student_chatbot_dialogs.c.conversation_id,
            student_chatbot_dialogs.c.unit_id,
            student_chatbot_dialogs.c.knowledge_point_id
        ).order_by(
            desc('last_message_at')
        )
        
        results = conn.execute(query).fetchall()
        
        conversations = [
            ConversationSummary(
                conversation_id=row.conversation_id,
                first_message=row.first_message or "",
                last_message_at=row.last_message_at,
                message_count=row.message_count,
                unit_id=row.unit_id,
                knowledge_point_id=row.knowledge_point_id
            )
            for row in results
        ]
        
        return GetConversationsResponse(
            conversations=conversations,
            total_count=len(conversations)
        )


@router.get("/conversations/{conversation_id}/messages", response_model=GetConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    student_id: int = Depends(get_current_user_id)
):
    """
    獲取對話歷史
    
    路徑參數：
    - conversation_id: 對話 ID
    
    查詢參數：
    - limit: 返回訊息數量（預設 50）
    - offset: 偏移量（預設 0）
    """
    # student_id 已經由 Depends 注入
    
    with engine.connect() as conn:
        # 查詢訊息
        query = select(
            student_chatbot_dialogs.c.id,
            student_chatbot_dialogs.c.role,
            student_chatbot_dialogs.c.content,
            student_chatbot_dialogs.c.created_at
        ).where(
            and_(
                student_chatbot_dialogs.c.student_id == student_id,
                student_chatbot_dialogs.c.conversation_id == conversation_id
            )
        ).order_by(
            student_chatbot_dialogs.c.created_at.asc()
        ).limit(limit).offset(offset)
        
        results = conn.execute(query).fetchall()
        
        if not results:
            raise HTTPException(status_code=404, detail="對話不存在或無權限訪問")
        
        messages = [
            DialogMessage(
                id=row.id,
                role=row.role,
                content=row.content,
                created_at=row.created_at
            )
            for row in results
        ]
        
        # 獲取總數
        count_query = select(func.count(student_chatbot_dialogs.c.id)).where(
            and_(
                student_chatbot_dialogs.c.student_id == student_id,
                student_chatbot_dialogs.c.conversation_id == conversation_id
            )
        )
        total_count = conn.execute(count_query).scalar()
        
        return GetConversationHistoryResponse(
            conversation_id=conversation_id,
            messages=messages,
            total_count=total_count
        )


@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: str,
    student_id: int = Depends(get_current_user_id)
):
    """
    刪除對話
    
    路徑參數：
    - conversation_id: 對話 ID
    """
    from backend.app.utils.mastery_cache import delete_mastery
    
    # student_id 已經由 Depends 注入
    
    with engine.connect() as conn:
        # 先查詢 course_id 以便清除快取
        course_id_result = conn.execute(text("""
            SELECT DISTINCT course_id 
            FROM student_chatbot_dialogs 
            WHERE conversation_id = :conv_id AND student_id = :student_id
            LIMIT 1
        """), {"conv_id": conversation_id, "student_id": student_id}).fetchone()
        
        course_id = course_id_result.course_id if course_id_result else None
        
        # 刪除該對話的所有訊息
        delete_stmt = delete(student_chatbot_dialogs).where(
            and_(
                student_chatbot_dialogs.c.student_id == student_id,
                student_chatbot_dialogs.c.conversation_id == conversation_id
            )
        )
        
        result = conn.execute(delete_stmt)
        deleted_count = result.rowcount
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="對話不存在或無權限刪除")
        
        conn.commit()
        
        # 清除精熟度快取
        if course_id:
            delete_mastery(student_id, course_id, conversation_id)
        
        return DeleteConversationResponse(
            success=True,
            deleted_count=deleted_count
        )


@router.get("/knowledge-mastery", response_model=GetKnowledgeMasteryResponse)
async def get_knowledge_mastery(
    course_id: int,
    unit_id: int,
    knowledge_point_id: Optional[int] = None,
    student_id: int = Depends(get_current_user_id)
):
    """
    獲取學生的知識點精熟度狀態
    
    查詢參數：
    - course_id: 課程 ID（必填）
    - unit_id: 章節 ID（必填）
    - knowledge_point_id: 知識點 ID（可選）
    """
    # student_id 已經由 Depends 注入
    
    with engine.connect() as conn:
        # 構建查詢條件（course_id 和 unit_id 必填）
        conditions = [
            student_knowledge_mastery.c.student_id == student_id,
            student_knowledge_mastery.c.course_id == course_id,
            student_knowledge_mastery.c.unit_id == unit_id
        ]
        
        if knowledge_point_id:
            conditions.append(student_knowledge_mastery.c.knowledge_point_id == knowledge_point_id)
        
        # 查詢精熟度記錄（JOIN knowledge_points 取得名稱）
        query = select(
            student_knowledge_mastery.c.unit_id,
            student_knowledge_mastery.c.knowledge_point_id,
            knowledge_points.c.name.label("knowledge_point_name"),
            student_knowledge_mastery.c.mastery_level,
            student_knowledge_mastery.c.preview_mastery_level,
            student_knowledge_mastery.c.review_mastery_level,
            student_knowledge_mastery.c.preview_completed,
            student_knowledge_mastery.c.review_completed,
            student_knowledge_mastery.c.last_assessed_at
        ).select_from(
            student_knowledge_mastery.outerjoin(
                knowledge_points,
                student_knowledge_mastery.c.knowledge_point_id == knowledge_points.c.id
            )
        ).where(
            and_(*conditions)
        ).order_by(
            student_knowledge_mastery.c.unit_id,
            student_knowledge_mastery.c.knowledge_point_id
        )
        
        results = conn.execute(query).fetchall()
        
        mastery_items = [
            KnowledgeMasteryItem(
                unit_id=row.unit_id,
                knowledge_point_id=row.knowledge_point_id,
                knowledge_point_name=row.knowledge_point_name,
                mastery_level=row.review_mastery_level or row.preview_mastery_level,
                preview_completed=row.preview_completed,
                review_completed=row.review_completed,
                last_assessed_at=row.last_assessed_at
            )
            for row in results
        ]
        
        return GetKnowledgeMasteryResponse(
            mastery_items=mastery_items,
            total_count=len(mastery_items)
        )
