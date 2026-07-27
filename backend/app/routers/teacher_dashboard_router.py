from fastapi import APIRouter, HTTPException, Query, Body, Depends
from backend.app.services.review_service import review_service
from backend.app.utils.auth_utils import get_current_user_id
from typing import List, Dict

router = APIRouter(
    prefix="/api/v1/teacher/dashboard",
    tags=["Teacher Dashboard"]
)

@router.get("/weak-points", response_model=List[Dict])
async def get_class_weak_points(
    unit_id: int = Query(..., description="單元 ID"),
    stage: str = Query("preview", description="階段: preview (課前) 或 review (課後)"),
    teacher_id: int = Depends(get_current_user_id)
):
    """
    取得班級在特定單元的弱項知識點 (多數決：待加強人數最多者)
    """
    try:
        weak_points = await review_service.get_class_weak_points(unit_id, stage)
        return weak_points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overview", response_model=Dict)
async def get_dashboard_overview(
    unit_id: int = Query(..., description="單元 ID"),
    stage: str = Query("preview", description="階段: preview (課前) 或 review (課後)"),
    teacher_id: int = Depends(get_current_user_id)
):
    """
    取得班級概覽數據 (各知識點掌握度分佈)。
    """
    try:
        data = await review_service.get_class_mastery_distribution(unit_id, stage)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/students", response_model=List[Dict])
async def get_at_risk_students_list(
    unit_id: int = Query(..., description="單元 ID"),
    stage: str = Query("preview", description="階段: preview (課前) 或 review (課後)"),
    risk_threshold: int = Query(2, description="弱項數量閾值"),
    show_all: bool = Query(False, description="是否顯示全班學生"),
    teacher_id: int = Depends(get_current_user_id)
):
    """
    取得關注學生名單 (At-risk students) 或全班名單。
    """
    try:
        data = await review_service.get_at_risk_students(unit_id, stage, risk_threshold, show_all)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/generate-review", response_model=Dict)
async def generate_class_review(
    payload: Dict = Body(..., example={"unit_id": 1, "weak_kp_ids": [1, 2, 3]}),
    teacher_id: int = Depends(get_current_user_id)
):
    """
    針對選定的弱項知識點，生成全班性的重點複習內容
    """
    unit_id = payload.get("unit_id")
    weak_kp_ids = payload.get("weak_kp_ids", [])
    
    if not unit_id:
        raise HTTPException(status_code=400, detail="Missing unit_id")
    
    try:
        review_content = await review_service.generate_class_review_content(unit_id, weak_kp_ids)
        return review_content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
