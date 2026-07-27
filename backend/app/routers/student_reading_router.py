from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id
from backend.app.utils.time_utils import get_now_taipei
import json

router = APIRouter(prefix="/api/student/reading", tags=["Student Reading"])

class ReadingLogCreate(BaseModel):
    unit_session_id: UUID
    content_id: int
    unit_id: int
    stay_duration_seconds: int
    max_scroll_depth: float
    citation_interactions: Optional[List[dict]] = None
    exit_action: Optional[str] = None # 'next_item', 'back_to_course'

@router.post("/logs")
async def create_reading_log(
    payload: ReadingLogCreate,
    student_id: int = Depends(get_current_user_id)
):
    """
    紀錄學生閱讀教材的細節（時長、捲動深度、引用互動）
    """
    def _sync_log():
        with engine.begin() as conn:
            query = text("""
                INSERT INTO material_reading_logs 
                (unit_session_id, user_id, content_id, unit_id, stay_duration_seconds, max_scroll_depth, citation_interactions, exit_action, created_at)
                VALUES 
                (:sid, :uid, :cid, :unit_id, :duration, :depth, :citations, :exit, :now)
            """)
            conn.execute(query, {
                "sid": payload.unit_session_id,
                "uid": student_id,
                "cid": payload.content_id,
                "unit_id": payload.unit_id,
                "duration": payload.stay_duration_seconds,
                "depth": payload.max_scroll_depth,
                "citations": json.dumps(payload.citation_interactions) if payload.citation_interactions else None,
                "exit": payload.exit_action,
                "now": get_now_taipei()
            })
            return True

    await run_in_db_pool(_sync_log)
    return {"message": "Reading log created successfully"}
