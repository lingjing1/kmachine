"""
學生 Chatbot LangGraph 工作流定義

架構設計：
我們採用 Sequential (順序) 執行模式，雖然邏輯上這三個檢索 Agent 是獨立的，
但為了讓後續 Agent 能利用前面 Agent 的輸出（例如 RAG 利用 Mastery 的 Weak Points），
我們安排了明確的資料流順序。

執行順序：
1. Start Node (初始化與檢查)
2. Dialog Agent (提取對話歷史)
   - Input: User Query
   - Output: Recent Dialogs, Condensed History
3. Mastery Agent (提取精熟度)
   - Input: Student ID, Unit ID
   - Output: Current Mastery, Weak Points (用於 RAG 加權)
4. Retrieval Agent (RAG 教材)
   - Input: User Query, Weak Points (from Mastery Agent)
   - Output: Retrieved Chunks
5. Scaffolding Agent (整合與生成)
   - Input: All Context
   - Output: Final Response, Scaffolding Strategy
6. Normalize Node (API Contract 保證)
   - Input: Final Result
   - Output: Normalized Result (保證 keys 存在)
   
錯誤處理：
每個節點執行後都會檢查 `error` 欄位，若有錯誤發生則直接中止流程。
"""

from typing import Literal, Dict, Callable
import time
from langgraph.graph import StateGraph, END
from backend.app.agents.student_agent.state import StudentAgentState

# Import nodes
from backend.app.agents.student_agent.nodes.start_node import start_node
from backend.app.agents.student_agent.nodes.dialog_agent import dialog_agent_node
from backend.app.agents.student_agent.nodes.mastery_agent import mastery_agent_node
from backend.app.agents.student_agent.nodes.retrieval_agent import retrieval_agent_node
from backend.app.agents.student_agent.nodes.scaffolding_agent import scaffolding_agent_node

def check_error(state: StudentAgentState) -> Literal["continue", "end"]:
    """檢查是否有錯誤發生"""
    if state.get("error"):
        return "end"
    return "continue"


def timed_node(node_fn: Callable, timing_key: str):
    """
    包裝 Agent Node，自動計時並將耗時寫入 state['agent_timings']。

    Args:
        node_fn: 原始的 node function
        timing_key: 計時 key 名稱，例如 "dialog_agent_ms"
    """
    def wrapper(state: StudentAgentState) -> Dict:
        start = time.perf_counter()
        result = node_fn(state)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Merge timing into existing agent_timings
        existing = state.get("agent_timings", {})
        updated = {**existing, timing_key: elapsed_ms}
        result["agent_timings"] = updated

        return result
    return wrapper


def normalize_agent_result(state: StudentAgentState) -> Dict:
    """
    最後一哩路：確保輸出的 keys 符合 API Contract
    避免因為中間某個 Agent 失敗或沒執行，導致前端拿不到必要欄位
    """
    return {
        "final_response": state.get("final_response") or "抱歉，系統暫時無法處理您的請求，請稍後再試。",
        "sources": state.get("sources", []),
        "scaffolding_strategy": state.get("scaffolding_strategy", "error_fallback"),
        "error": state.get("error"),
        # Turn log data pass-through
        "agent_timings": state.get("agent_timings", {}),
        "full_prompt": state.get("full_prompt"),
        "rag_candidates_count": state.get("rag_candidates_count", 0),
        "environmental_impact": state.get("environmental_impact"),
    }

def build_student_agent_graph():
    workflow = StateGraph(StudentAgentState)
    
    # 1. 註冊節點（使用 timed_node 包裝以記錄各 Agent 耗時）
    workflow.add_node("start_node", start_node)
    workflow.add_node("dialog_agent", timed_node(dialog_agent_node, "dialog_agent_ms"))
    workflow.add_node("mastery_agent", timed_node(mastery_agent_node, "mastery_agent_ms"))
    workflow.add_node("retrieval_agent", timed_node(retrieval_agent_node, "retrieval_agent_ms"))
    workflow.add_node("scaffolding_agent", timed_node(scaffolding_agent_node, "scaffolding_agent_ms"))
    workflow.add_node("normalize_node", normalize_agent_result)
    
    # 2. 設定邊與執行順序 (含錯誤處理)
    
    # Start -> Dialog
    workflow.set_entry_point("start_node")
    
    workflow.add_conditional_edges(
        "start_node",
        check_error,
        {
            "continue": "dialog_agent",
            "end": "normalize_node"  # 錯誤時直接去 normalize
        }
    )
    
    # Dialog -> Mastery
    workflow.add_conditional_edges(
        "dialog_agent",
        check_error,
        {
            "continue": "mastery_agent",
            "end": "normalize_node"
        }
    )
    
    # Mastery -> Retrieval
    workflow.add_conditional_edges(
        "mastery_agent",
        check_error,
        {
            "continue": "retrieval_agent",
            "end": "normalize_node"
        }
    )
    
    # Retrieval -> Scaffolding
    workflow.add_conditional_edges(
        "retrieval_agent",
        check_error,
        {
            "continue": "scaffolding_agent",
            "end": "normalize_node"
        }
    )
    
    # Scaffolding -> Normalize
    workflow.add_edge("scaffolding_agent", "normalize_node")
    
    # Normalize -> END
    workflow.add_edge("normalize_node", END)
    
    return workflow.compile()

# 建立編譯後的 app 實例
student_agent_app = build_student_agent_graph()
