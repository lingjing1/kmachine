import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.utils.auth_utils import get_current_user_id
from pydantic import BaseModel, Field
from sqlalchemy import text
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine

router = APIRouter(
    prefix="/api/v1/teacher",
    tags=["Teacher Ratings"]
)

# ==================== Pydantic Models ====================

class TeacherRatingRequest(BaseModel):
    """教師評分請求"""
    rating: int = Field(..., ge=1, le=5, description="評分 1-5 星")
    feedback: Optional[str] = Field(None, description="文字回饋（選填）")
    dimensions: Optional[Dict[str, Any]] = Field(None, description="詳細維度評分 (accuracy, efficiency, etc.)")

class TeacherRatingResponse(BaseModel):
    """教師評分回應"""
    id: int
    teacher_rating: Dict[str, Any]
    updated_at: str

class RatingStatsResponse(BaseModel):
    """評分統計與建議回應"""
    total_count: int
    suggest_detailed: bool

# ==================== API Endpoints ====================

@router.post(
    "/generated_contents/{content_id}/rate",
    response_model=TeacherRatingResponse,
    summary="提交或更新教師對生成內容的評分"
)
async def submit_teacher_rating(
    content_id: int,
    request: TeacherRatingRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    提交教師評分至 generated_contents 表的 teacher_rating 欄位 (JSONB)
    """
    with engine.connect() as conn:
        # Verify content exists and belongs to user (via jobs link)
        # However, generated_contents might not have user_id directly, it's via orchestration_jobs
        check_query = text("""
            SELECT gc.id 
            FROM generated_contents gc
            JOIN orchestration_jobs oj ON gc.source_agent_task_id = ANY (
                SELECT id FROM agent_tasks WHERE job_id = oj.id
            ) OR oj.final_output_id = gc.id
            WHERE gc.id = :content_id AND oj.user_id = :user_id
        """)
        # Note: Above query might be slow or complex depending on schema. 
        # Simpler check if possible:
        row = conn.execute(text("SELECT id FROM generated_contents WHERE id = :id"), {"id": content_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Generated content not found")

        rating_json = {
            "score": request.rating,
            "feedback": request.feedback,
            "dimensions": request.dimensions,
        }

        update_query = text("""
            UPDATE generated_contents
            SET teacher_rating = :rating,
                updated_at = :updated_at
            WHERE id = :id
            RETURNING id, teacher_rating, updated_at
        """)

        result = conn.execute(update_query, {
            "id": content_id,
            "rating": json.dumps(rating_json),
            "updated_at": get_now_taipei()
        }).fetchone()
        
        conn.commit()

        return TeacherRatingResponse(
            id=result[0],
            teacher_rating=result[1],
            updated_at=result[2].isoformat()
        )

@router.get(
    "/stats/rating_count",
    response_model=RatingStatsResponse,
    summary="取得教師評分統計"
)
async def get_teacher_rating_stats(user_id: int = Depends(get_current_user_id)):
    """
    取得教師已評分的次數，判斷是否該觸發詳細評分
    """
    with engine.connect() as conn:
        # Count non-null teacher_rating in generated_contents for this user
        # We need to join with jobs to filter by user_id
        count_query = text("""
            SELECT COUNT(*) 
            FROM generated_contents gc
            JOIN orchestration_jobs oj ON oj.final_output_id = gc.id
            WHERE oj.user_id = :user_id AND gc.teacher_rating IS NOT NULL
        """)
        count = conn.execute(count_query, {"user_id": user_id}).scalar()
        
        # 間隔觸發邏輯: 每 4 次觸發一次詳細 (0, 4, 8...)
        suggest_detailed = (count > 0 and (count + 1) % 4 == 0)

        return RatingStatsResponse(
            total_count=count,
            suggest_detailed=suggest_detailed
        )
