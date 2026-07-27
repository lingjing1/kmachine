from fastapi import APIRouter, Query, HTTPException, Body, Depends
from typing import Optional, List
from backend.app.utils.auth_utils import get_current_user_id
from backend.app.services.dashboard_service import get_dashboard_data
from backend.app.schemas.dashboard_schemas import DashboardResponse
from backend.app.schemas.lime_schemas import LimeReportResponse
from backend.app.services.lime_explainer_service import get_lime_report_json
from backend.app.services.review_service import review_service
from backend.app.utils.db_logger import engine
from sqlalchemy import text
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei
import json

router = APIRouter(
    prefix="/api/v1/student/dashboard",
    tags=["Student Dashboard"]
)

# NOTE: Review endpoints have been migrated to student_review_router.py
# - GET /api/student/review/units/{unit_id}/summary
# - POST /api/student/review/units/{unit_id}/quiz

@router.get("/", response_model=DashboardResponse)
async def dashboard(
    course_id: int = Query(..., description="課程 ID"),
    unit_id: int = Query(..., description="單元 ID"),
    student_id: Optional[int] = Query(None, description="學生 ID（由 Token 提供，教用可傳入）"),
    stage: str = Query("preview", description="階段: preview 或 review"),
    current_user_id: int = Depends(get_current_user_id)
):
    student_id = student_id or current_user_id
    data = await get_dashboard_data(course_id, unit_id, student_id, stage)
    if not data:
        raise HTTPException(status_code=404, detail="找不到儀表板資料")
    return data


@router.get("/kps/{kp_id}/lime-report", response_model=LimeReportResponse)
async def get_lime_report(
    kp_id: int,
    student_id: Optional[int] = Query(None, description="學生 ID（由 Token 提供，教用可傳入）"),
    stage: str = Query("preview", description="階段: preview 或 review"),
    current_user_id: int = Depends(get_current_user_id)
):
    student_id = student_id or current_user_id
    """
    取得 LIME 報告 JSON 格式（只讀快取，不即時生成）
    
    Args:
        kp_id: 知識點 ID
        student_id: 學生 ID
        stage: 階段 ('preview' 或 'review')
    
    Returns:
        LimeReportResponse 包含特徵權重與高亮文本，或 not_ready 狀態
    """
    import os
    
    # 讀取快取（新路徑：kp_X/latest.json）
    user_dir = f"user_id_{student_id}"
    json_cache_path = os.path.join(
        "backend", "lime_reports", user_dir, stage, f"kp_{kp_id}", "latest.json"
    )
    
    # 向下相容舊路徑（若新路徑不存在，嘗試舊路徑）
    legacy_path = os.path.join("backend", "lime_reports", user_dir, stage, f"knowledge_point_{kp_id}.json")
    
    actual_path = json_cache_path if os.path.exists(json_cache_path) else (legacy_path if os.path.exists(legacy_path) else None)
    
    if actual_path:
        try:
            with open(actual_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            with engine.connect() as conn:
                kp_info = conn.execute(text("""
                    SELECT name FROM knowledge_points WHERE id = :kp_id
                """), {"kp_id": kp_id}).fetchone()
                kp_name = kp_info[0] if kp_info else f"知識點 {kp_id}"
            
            # feature_weights: JSON 存的是 {keyword: weight} dict，需轉成 List[FeatureWeight]
            raw_fw = cached_data.get('feature_weights', [])
            if isinstance(raw_fw, dict):
                feature_weights_list = [
                    {"keyword": k, "weight": v} for k, v in raw_fw.items()
                ]
            else:
                # 已經是 list 格式
                feature_weights_list = raw_fw
            
            # highlighted_text: 若是空 dict 或缺少必填欄位，設為 None
            raw_ht = cached_data.get('highlighted_text')
            if isinstance(raw_ht, dict) and raw_ht.get('original') and 'highlights' in raw_ht:
                highlighted_text_val = raw_ht
            else:
                highlighted_text_val = None
            
            return LimeReportResponse(
                knowledge_point_id=kp_id,
                knowledge_point_name=kp_name,
                stage=stage,
                feature_weights=feature_weights_list,
                highlighted_text=highlighted_text_val,
                generated_at=cached_data.get('generated_at', get_now_taipei().isoformat())
            )
        except Exception as e:
            print(f"Cache read error: {e}")
    
    # 報告尚未生成
    raise HTTPException(
        status_code=404,
        detail="LIME 報告尚未生成，請先完成練習並等待系統分析完成（約 30 秒）"
    )


@router.get("/courses/{course_id}/units", response_model=list[dict])
def get_course_units(course_id: int):
    """取得課程的所有單元列表"""
    with engine.connect() as conn:
        stmt = text("""
            SELECT id, name, topic_id
            FROM course_units
            WHERE course_id = :course_id
            ORDER BY topic_id
        """)
        rows = conn.execute(stmt, {"course_id": course_id}).fetchall()
        
    return [
        {"id": row.id, "name": row.name, "topic_id": row.topic_id} 
        for row in rows
    ]
