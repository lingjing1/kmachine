from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import Table, select, and_
from backend.app.utils.db_logger import engine, metadata
from backend.app.agents.student_agent.state import StudentAgentState
from backend.app.agents.student_agent.nodes.start_node import create_error

# === Table Reflection (Lazy Loading) ===
_mastery_table_cache = None
_knowledge_points_cache = None

def get_mastery_table() -> Table:
    """Lazy load student_knowledge_mastery table"""
    global _mastery_table_cache
    if _mastery_table_cache is None:
        _mastery_table_cache = Table('student_knowledge_mastery', metadata, autoload_with=engine)
    return _mastery_table_cache

def get_knowledge_points_table() -> Table:
    """Lazy load knowledge_points table"""
    global _knowledge_points_cache
    if _knowledge_points_cache is None:
        _knowledge_points_cache = Table('knowledge_points', metadata, autoload_with=engine)
    return _knowledge_points_cache

# === Helper Functions ===

def get_unit_mastery_status(
    student_id: int, 
    unit_id: Optional[int],
) -> List[Dict]:
    """
    取得同一單元下所有知識點的精熟度 (含知識點名稱)
    
    這是主要的精熟度查詢函數。改為回傳整個 unit 的所有 KP 精熟度，
    而非單一知識點，以符合以下使用情境：
    - 預習/複習教材（一份教材涵蓋多個 KP）
    - 閱讀上傳附件（無特定 KP）
    - 撰寫作業（可能跨多個 KP）
    """
    if not unit_id:
        return []
    
    student_knowledge_mastery = get_mastery_table()
    knowledge_points = get_knowledge_points_table()
    
    with engine.connect() as conn:
        # Join mastery table with knowledge_points table to get names
        stmt = select(
            student_knowledge_mastery.c.knowledge_point_id,
            student_knowledge_mastery.c.mastery_level,
            student_knowledge_mastery.c.preview_mastery_level,
            student_knowledge_mastery.c.review_mastery_level,
            student_knowledge_mastery.c.preview_completed,
            student_knowledge_mastery.c.review_completed,
            student_knowledge_mastery.c.last_assessed_at,
            knowledge_points.c.name.label("knowledge_point_name")
        ).select_from(
            student_knowledge_mastery.join(
                knowledge_points,
                student_knowledge_mastery.c.knowledge_point_id == knowledge_points.c.id
            )
        ).where(
            and_(
                student_knowledge_mastery.c.student_id == student_id,
                student_knowledge_mastery.c.unit_id == unit_id
            )
        )
        
        results = conn.execute(stmt).fetchall()
        
        mastery_list = []
        for row in results:
            effective_level = row.review_mastery_level or row.preview_mastery_level
            last_assessed = row.last_assessed_at
            if isinstance(last_assessed, datetime):
                last_assessed = last_assessed.isoformat()
            mastery_list.append({
                "knowledge_point_id": row.knowledge_point_id,
                "knowledge_point_name": row.knowledge_point_name,
                "mastery_level": effective_level,
                "preview_mastery_level": row.preview_mastery_level,
                "review_mastery_level": row.review_mastery_level,
                "preview_completed": row.preview_completed,
                "review_completed": row.review_completed,
                "last_assessed_at": last_assessed
            })
        return mastery_list


# === Node Definition ===

# Removed @log_task to avoid using teacher-side db_logger
def mastery_agent_node(state: StudentAgentState) -> Dict:
    """
    Mastery Agent Node (Student Side)
    
    職責：
    1. 取得該單元下所有知識點的精熟度並回傳為 list。
    2. 識別弱點知識點（精熟度為「待加強」）以便在 RAG 中進行加權。
    
    策略：不再依賴 knowledge_point_id，改為查詢整個 unit 的精熟度，
    符合「一份教材包含多個 KP」的實際使用情境。
    
    輸入：
    - student_id
    - unit_id

    輸出 (更新)：
    - current_mastery: List[Dict]  — 單元內所有 KP 精熟度
    - weak_points: List[str]       — 精熟度為「待加強」的 KP 名稱列表
    """
    try:
        student_id = state["student_id"]
        unit_id = state.get("unit_id")
        
        # === 快取檢查：current_mastery 是非空 list 就代表快取命中 ===
        cached_mastery = state.get("current_mastery")
        if isinstance(cached_mastery, list) and len(cached_mastery) > 0:
            print(f"[Mastery Agent] Using cached mastery ({len(cached_mastery)} KPs)")
            return {}
        
        # === 首次查詢：從 DB 獲取整個單元所有 KP 精熟度 ===
        if not unit_id:
            return {
                "current_mastery": [],
                "weak_points": []
            }

        unit_mastery = get_unit_mastery_status(student_id, unit_id)
        
        # 識別弱點知識點：篩選精熟度為「待加強」的 KP
        weak_points = [
            m["knowledge_point_name"]
            for m in unit_mastery
            if m.get("mastery_level") in ["待加強", "Needs Improvement"]
        ]
        
        return {
            "current_mastery": unit_mastery,
            "weak_points": weak_points
        }
        
    except Exception as e:
        print(f"Error in mastery_agent_node: {e}")
        # Mastery is optional context, so we can return empty if fails
        return {
            "current_mastery": [],
            "weak_points": [],
        }
