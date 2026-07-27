from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id
from backend.app.utils.time_utils import get_now_taipei

router = APIRouter(prefix="/api/student/sessions", tags=["Student Session"])

class SessionStartRequest(BaseModel):
    course_id: int
    unit_id: int
    context_data: Optional[Dict[str, Any]] = None

@router.post("/start")
async def start_session(
    payload: SessionStartRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    開始一個新的學習 Session，並返回唯一的 session_id
    """
    session_id = uuid4()
    
    def _db_start_session():
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO student_learning_sessions (id, user_id, course_id, unit_id, started_at, last_active_at, context_data)
                VALUES (:id, :uid, :cid, :unit_id, :now, :now, :ctx)
            """), {
                "id": session_id,
                "uid": student_id,
                "cid": payload.course_id,
                "unit_id": payload.unit_id,
                "ctx": sa_json_dumps(payload.context_data) if payload.context_data else None,
                "now": get_now_taipei()
            })
        return str(session_id)

    # Note: Need helper for JSON if using pure sqlalchemy text
    import json
    def sa_json_dumps(data):
        return json.dumps(data)

    res_id = await run_in_db_pool(_db_start_session)
    return {"session_id": res_id}

@router.post("/{session_id}/heartbeat")
async def heartbeat(
    session_id: UUID,
    student_id: int = Depends(get_current_user_id)
):
    """
    更新 Session 的最後活躍時間
    """
    def _db_heartbeat():
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE student_learning_sessions 
                SET last_active_at = :now 
                WHERE id = :id AND user_id = :uid
            """), {"id": session_id, "uid": student_id, "now": get_now_taipei()})
        return True
    
    await run_in_db_pool(_db_heartbeat)
    return {"status": "ok"}
