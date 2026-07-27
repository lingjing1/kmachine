import yaml
import os
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from backend.app.utils.auth_utils import get_current_user
from backend.app.db import engine

router = APIRouter(
    prefix="/api/feedback",
    tags=["feedback"]
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "feedback_config.yaml")

# ==================== Pydantic Models ====================

class FAQItem(BaseModel):
    id: int
    question: str
    answer: str
    role: str
    category: Optional[str] = None

class ProblemType(BaseModel):
    id: str
    label: str
    category: Optional[str] = None

class FeedbackConfigResponse(BaseModel):
    faqs: List[FAQItem]
    problem_types: List[ProblemType]

class FeedbackReportRequest(BaseModel):
    selected_problems: Optional[List[str]] = Field(None, description="選中的問題類型 ID 列表")
    description: str = Field(..., description="自定義問題描述")

# ==================== API Endpoints ====================

@router.get("/config", response_model=FeedbackConfigResponse)
async def get_feedback_config(user: dict = Depends(get_current_user)):
    """
    讀取靜態 YAML 配置並回傳過濾後的 FAQ 與問題類型
    """
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail="Feedback configuration not found")
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 根據使用者角色過濾 FAQ
        user_role = user.get("role", "student").lower()
        all_faqs = config.get("faqs", [])
        
        filtered_faqs = []
        for faq in all_faqs:
            faq_role = faq.get("role", "all").lower()
            if faq_role == "all" or faq_role == user_role:
                filtered_faqs.append(faq)
        
        return {
            "faqs": filtered_faqs,
            "problem_types": config.get("problem_types", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading config: {str(e)}")

@router.post("/report", status_code=status.HTTP_201_CREATED)
async def submit_feedback_report(request: FeedbackReportRequest, user: dict = Depends(get_current_user)):
    """
    提交回饋報告並存入資料庫
    """
    user_id = user.get("user_id")
    user_role = user.get("role", "student")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    try:
        with engine.connect() as conn:
            query = text("""
                INSERT INTO feedback_reports 
                (user_id, user_role, selected_problems, description, status, created_at)
                VALUES 
                (:user_id, :user_role, :selected_problems, :description, 'pending', :created_at)
            """)
            
            from backend.app.utils.time_utils import get_now_taipei
            conn.execute(query, {
                "user_id": user_id,
                "user_role": user_role,
                "selected_problems": json.dumps(request.selected_problems) if request.selected_problems else None,
                "description": request.description,
                "created_at": get_now_taipei()
            })
            conn.commit()
            
        return {"status": "success", "message": "Feedback submitted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
