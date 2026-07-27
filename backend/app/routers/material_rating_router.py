import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.utils.auth_utils import get_current_user_id
from pydantic import BaseModel, Field
from sqlalchemy import text
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine

router = APIRouter(
    prefix="/api/student",
    tags=["material-ratings"]
)


# ==================== Pydantic Models ====================

class MaterialRatingRequest(BaseModel):
    """教材評分請求"""
    rating: int = Field(..., ge=1, le=5, description="評分 1-5 星")
    feedback: Optional[str] = Field(None, description="文字回饋（選填）")
    dimensions: Optional[Dict[str, Any]] = Field(None, description="詳細維度評分")


class BatchMaterialRatingRequest(BaseModel):
    """教材批次評分請求"""
    content_ids: list[int] = Field(..., description="教材 ID 列表")
    rating: int = Field(..., ge=1, le=5, description="評分 1-5 星")
    feedback: Optional[str] = Field(None, description="文字回饋（選填）")
    dimensions: Optional[Dict[str, Any]] = Field(None, description="詳細維度評分")


class MaterialRatingResponse(BaseModel):
    """教材評分回應"""
    id: int
    user_id: int
    course_id: int
    content_id: int
    rating: Dict[str, Any]  # JSONB: {score, feedback, dimensions...}
    created_at: str
    updated_at: str

class RatingStatsResponse(BaseModel):
    """評分統計與建議回應"""
    total_count: int
    suggest_detailed: bool


# ==================== API Endpoints ====================

@router.get(
    "/stats/rating_count",
    response_model=RatingStatsResponse,
    summary="取得學生教材評分統計"
)
async def get_student_rating_stats(user_id: int = Depends(get_current_user_id)):
    """
    取得學生已評分的總次數，用於判斷是否觸發詳細評分
    """
    with engine.connect() as conn:
        count_query = text("""
            SELECT COUNT(*) FROM material_ratings WHERE user_id = :user_id
        """)
        count = conn.execute(count_query, {"user_id": user_id}).scalar()
        
        # 間隔觸發邏輯: 每 4 次觸發一次詳細
        suggest_detailed = (count > 0 and (count + 1) % 4 == 0)

        return RatingStatsResponse(
            total_count=count,
            suggest_detailed=suggest_detailed
        )


# ==================== API Endpoints ====================

@router.post(
    "/materials/{content_id}/rate",
    response_model=MaterialRatingResponse,
    summary="提交或更新教材評分"
)
async def submit_material_rating(
    content_id: int,
    request: MaterialRatingRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    提交或更新教材評分（UPSERT）
    
    - **content_id**: course_contents.id
    - **rating**: 1-5 星評分
    - **feedback**: 文字回饋（選填）
    """
    with engine.connect() as conn:
        # 1. 取得 course_id
        course_query = text("""
            SELECT cc.course_id
            FROM course_contents cc
            WHERE cc.id = :content_id
        """)
        course_row = conn.execute(course_query, {"content_id": content_id}).fetchone()
        
        if not course_row:
            raise HTTPException(status_code=404, detail="Content not found")
        
        course_id = course_row[0]
        
        # 2. UPSERT rating (JSONB)
        # Construct JSON object
        rating_json = {
            "score": request.rating,
            "feedback": request.feedback,
            "dimensions": request.dimensions
        }
        
        upsert_query = text("""
            INSERT INTO material_ratings 
            (user_id, course_id, content_id, rating, created_at, updated_at)
            VALUES 
            (:user_id, :course_id, :content_id, :rating, :created_at, :updated_at)
            ON CONFLICT (user_id, content_id)
            DO UPDATE SET
                rating = EXCLUDED.rating,
                updated_at = EXCLUDED.updated_at
            RETURNING id, user_id, course_id, content_id, rating, 
                      created_at, updated_at
        """)
        
        now_local = get_now_taipei()
        result = conn.execute(upsert_query, {
            "user_id": user_id,
            "course_id": course_id,
            "content_id": content_id,
            "rating": json.dumps(rating_json),
            "created_at": now_local,
            "updated_at": now_local
        }).fetchone()
        
        conn.commit()
        
        return MaterialRatingResponse(
            id=result[0],
            user_id=result[1],
            course_id=result[2],
            content_id=result[3],
            rating=result[4],
            created_at=result[5].isoformat(),
            updated_at=result[6].isoformat()
        )


@router.post(
    "/materials/batch-rate",
    summary="批次提交或更新教材評分"
)
async def batch_submit_material_rating(
    request: BatchMaterialRatingRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    批次提交或更新教材評分（UPSERT）
    """
    import logging
    logger = logging.getLogger("uvicorn.error")
    
    logger.info(f"[BatchRate] User {user_id} rating contents: {request.content_ids}")
    
    if not request.content_ids:
        logger.warning(f"[BatchRate] No content_ids provided by user {user_id}")
        raise HTTPException(status_code=400, detail="No content_ids provided")

    with engine.connect() as conn:
        # 1. 取得所有 content_id 對應的 course_id
        # Use ANY(:ids) for PostgreSQL list binding
        course_query = text("""
            SELECT id, course_id
            FROM course_contents
            WHERE id = ANY(:content_ids)
        """)
        rows = conn.execute(course_query, {"content_ids": request.content_ids}).fetchall()
        
        logger.info(f"[BatchRate] Found {len(rows)} matching contents in DB")
        
        content_to_course = {row[0]: row[1] for row in rows}
        
        # 2. 構建 JSON 對象
        rating_json = {
            "score": request.rating,
            "feedback": request.feedback,
            "dimensions": request.dimensions
        }
        rating_str = json.dumps(rating_json)
        
        # 3. 逐一 UPSERT
        upsert_query = text("""
            INSERT INTO material_ratings 
            (user_id, course_id, content_id, rating, created_at, updated_at)
            VALUES 
            (:user_id, :course_id, :content_id, :rating, :created_at, :updated_at)
            ON CONFLICT (user_id, content_id)
            DO UPDATE SET
                rating = EXCLUDED.rating,
                updated_at = EXCLUDED.updated_at
        """)
        
        now_local = get_now_taipei()
        upsert_count = 0
        for content_id in request.content_ids:
            if content_id not in content_to_course:
                logger.warning(f"[BatchRate] content_id {content_id} not found in course_contents")
                continue
            
            conn.execute(upsert_query, {
                "user_id": user_id,
                "course_id": content_to_course[content_id],
                "content_id": content_id,
                "rating": rating_str,
                "created_at": now_local,
                "updated_at": now_local
            })
            upsert_count += 1
        
        conn.commit()
        logger.info(f"[BatchRate] Successfully upserted {upsert_count} ratings")
        
    return {"status": "success", "count": upsert_count}


@router.get(
    "/materials/{content_id}/rating",
    response_model=Optional[MaterialRatingResponse],
    summary="取得學生對教材的評分"
)
async def get_material_rating(
    content_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """
    取得學生自己對此教材的評分記錄
    
    - **content_id**: course_contents.id
    """
    with engine.connect() as conn:
        query = text("""
            SELECT id, user_id, course_id, content_id, rating, 
                   created_at, updated_at
            FROM material_ratings
            WHERE user_id = :user_id AND content_id = :content_id
        """)
        
        result = conn.execute(query, {
            "user_id": user_id,
            "content_id": content_id
        }).fetchone()
        
        if not result:
            return None
        
        return MaterialRatingResponse(
            id=result[0],
            user_id=result[1],
            course_id=result[2],
            content_id=result[3],
            rating=result[4],
            created_at=result[5].isoformat(),
            updated_at=result[6].isoformat()
        )
