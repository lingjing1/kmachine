from typing import TypedDict, List, Dict, Optional, Any

class StudentAgentInput(TypedDict):
    """最開始必須輸入的欄位"""
    student_id: int
    course_id: int
    conversation_id: str
    user_query: str
    # 這些雖然是 Optional，但在 Input 階段如果有就要傳
    unit_id: Optional[int]
    knowledge_point_id: Optional[int]
    attachment_id: Optional[int]   # 閱讀附件時傳入 (AttachmentViewer)
    content_id: Optional[int]      # 閱讀預習/複習教材時傳入 (TopicPreview)
    job_id: int

class StudentAgentState(StudentAgentInput, total=False):
    """
    完整的 State 定義
    
    繼承自 StudentAgentInput (必須欄位)
    其他欄位為 total=False (在 Graph 執行過程中逐步產生)
    """
    
    # === Dialog Agent 輸出 ===
    recent_dialogs: List[Dict]        # 最近對話（當前 conversation）
    related_dialogs: List[Dict]       # 跨知識點相關對話（語意搜尋）
    condensed_history: str            # 濃縮後的對話歷史
    
    # === Mastery Agent 輸出 ===
    current_mastery: List[Dict]       # 單元內所有知識點精熟度 (List of KP mastery dicts)
    weak_points: List[str]            # 需加強的知識點列表（用於 retrieval boost）
    
    # === Retrieval Agent 輸出 ===
    retrieved_chunks: List[Dict]      # RAG 檢索結果
    chunk_sources: List[Dict]         # 來源標註（用於引用）
    
    # === Scaffolding Agent 輸出 ===
    scaffolding_strategy: Optional[str]  # 選擇的引導策略
    final_response: Optional[str]        # 最終回應
    sources: List[Dict]                  # 引用來源（最後返回給前端的格式）
    
    # === Turn Log Data (for student_chatbot_turn_logs) ===
    agent_timings: Dict[str, int]      # Per-agent latency: {"dialog_agent_ms": 123, ...}
    full_prompt: Optional[str]         # 完整送給 LLM 的 prompt（研究用）
    rag_candidates_count: int          # RAG 初始檢索候選數量
    detected_knowledge_point_id: Optional[int] # AI 判讀出的知識點 ID
    environmental_impact: Optional[Dict]       # EcoLogits 碳排資料（carbon_g, energy_kwh 等）
    model_name: Optional[str]                  # LLM 模型名稱（如 gpt-4o-mini）

    # === Metadata & Error handling ===
    error: Optional[Dict]             # Structured error: {"code": str, "message": str, "details": Dict}
    usage: Dict[str, int]             # Token usage: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    metadata: Optional[Dict]          # tokens, latency, etc.
