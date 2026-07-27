from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional, List, Dict, Any

from backend.app.agents.debugging.oj_models import get_problems_by_chapter, get_problem_by_id

# 建立 Router
router = APIRouter(
    prefix="/debugging/problems", 
    tags=["Debugging Problems"]
)

@router.get("/chapter/{chapter_id}")
def list_problems_by_chapter_endpoint(
    chapter_id: str = Path(..., description="章節 ID，例如 C1"),
    start_time: Optional[str] = Query(None, description="開始時間 (YYYY-MM-DDTHH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="結束時間 (YYYY-MM-DDTHH:MM:SS)")
):
    try:
        problems = get_problems_by_chapter(chapter_id, start_time=start_time, end_time=end_time)
        return problems
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{problem_id}")
def get_problem_endpoint(
    problem_id: str = Path(..., description="題目 ID，例如 C1_P_1")
):
    try:
        problem = get_problem_by_id(problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail="Problem not found")
        return problem
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))