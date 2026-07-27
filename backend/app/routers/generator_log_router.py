from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
import json
from sqlalchemy import insert, text

from backend.app.utils.db_logger import engine, generator_setting_logs
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id

router = APIRouter(prefix="/api/v1/teacher/generator-logs", tags=["Teacher Action Logs"])

class GeneratorLogCreate(BaseModel):
    session_id: UUID = Field(..., description="Unique ID for the setting session")
    job_id: Optional[int] = Field(None, description="Linked Job ID if action led to generation")
    action_config: Dict[str, Any] = Field(default_factory=dict, description="Action parameters and details")
    duration_sec: Optional[float] = Field(None, description="Duration of action in seconds")

@router.post("")
async def create_generator_log(
    payload: GeneratorLogCreate,
    user_id: int = Depends(get_current_user_id)
):
    """
    Record teacher actions on the Generator Settings page.
    Used for RQ2 to track trust, efficiency, and pre-generation behavioral patterns.
    """
    def _sync_insert():
        with engine.begin() as conn:
            stmt = insert(generator_setting_logs).values(
                user_id=user_id,
                job_id=payload.job_id,
                session_id=payload.session_id,
                action_config=payload.action_config,
                duration_sec=payload.duration_sec
            )
            conn.execute(stmt)
            return True

    try:
        await run_in_db_pool(_sync_insert)
        return {"status": "success", "message": "Log recorded"}
    except Exception as e:
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.error(f"Failed to record generator log: {e}")
        raise HTTPException(status_code=500, detail=str(e))
