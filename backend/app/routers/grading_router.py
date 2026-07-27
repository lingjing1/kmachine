"""
Grading System API: 成績系統相關的 API
處理作業/考試配分設定、成績計算、查詢與修改 (Unified: 使用 course_contents 表)
"""
import logging
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.time_utils import get_now_taipei

logger = logging.getLogger(__name__)

# 建立獨立的 Router
router = APIRouter(prefix="/api/courses", tags=["Grades"])

# ==================== Pydantic Schemas ====================

class GradingConfigUpdate(BaseModel):
    """配分設定更新請求"""
    include_in_grade: bool
    weight: float  # 0-100
    total_points: float

class QuestionTypeGrading(BaseModel):
    """題型配分"""
    type_id: str
    type_name: str
    question_count: int
    points_per_question: float
    total_points: float
    auto_gradable: bool

class QuestionGrading(BaseModel):
    """題目配分設定"""
    total_points: float
    grading_method: str  # 'by_question_type' | 'by_individual_question'
    question_types: List[QuestionTypeGrading]

class GradingOverviewResponse(BaseModel):
    """配分總覽回應"""
    course_id: int
    assignments: List[Dict[str, Any]]
    exams: List[Dict[str, Any]]
    total_weight: float
    is_valid: bool

# ==================== Content Grading Helpers ====================

def _sync_update_content_grading(course_id: int, content_id: int, include_in_grade: bool, weight: float, total_points: float):
    with engine.connect() as conn:
        # 檢查是否存在 (Unified: course_contents)
        check_query = text("SELECT id FROM course_contents WHERE id = :id AND course_id = :cid")
        exists = conn.execute(check_query, {"id": content_id, "cid": course_id}).fetchone()
        
        if not exists:
            return None
        
        # 更新配分
        update_query = text("""
            UPDATE course_contents 
            SET include_in_grade = :include_in_grade,
                weight = :weight,
                total_points = :total_points,
                updated_at = :now
            WHERE id = :id
            RETURNING id, title, include_in_grade, weight, total_points
        """)
        result = conn.execute(update_query, {
            "id": content_id,
            "include_in_grade": include_in_grade,
            "weight": weight,
            "total_points": total_points,
            "now": get_now_taipei()
        })
        conn.commit()
        
        row = result.fetchone()
        
        return {
            "id": row.id,
            "title": row.title,
            "include_in_grade": row.include_in_grade,
            "weight": float(row.weight or 0),
            "total_points": float(row.total_points or 0)
        }

def _sync_update_content_question_grading(course_id: int, content_id: int, question_grading_dict: dict, total_points_check: float):
    with engine.connect() as conn:
        # Check existence & total_points
        check_query = text("SELECT id, total_points, content FROM course_contents WHERE id = :id AND course_id = :cid")
        row = conn.execute(check_query, {"id": content_id, "cid": course_id}).fetchone()
        
        if not row:
            return None, "內容不存在"
            
        current_total = float(row.total_points or 0)
        current_content = row.content or {}
        
        # Validate total points
        if abs(total_points_check - current_total) > 0.01:
            return None, f"題目配分總和 ({total_points_check}) 與總分 ({current_total}) 不一致"
            
        # Merge question_grading into content JSON
        if isinstance(current_content, dict):
            current_content['question_grading'] = question_grading_dict
        elif isinstance(current_content, list):
            # If it's a list, we can't easily inject it into the list itself 
            # while maintaining the "flattened" list contract.
            # However, the DB schema has a dedicated 'question_grading' column.
            # We should update BOTH for backward compatibility if possible,
            # but updating the column is most important for the new flow.
            pass
        else:
            current_content = {'question_grading': question_grading_dict}
            
        # Update (Update both content column and question_grading column)
        update_query = text("""
            UPDATE course_contents 
            SET content = CAST(:content_json AS json),
                question_grading = CAST(:qgrading_json AS json),
                updated_at = :now
            WHERE id = :id
        """)
        conn.execute(update_query, {
            "id": content_id,
            "content_json": json.dumps(current_content),
            "qgrading_json": json.dumps(question_grading_dict),
            "now": get_now_taipei()
        })
        conn.commit()
        
        return {
            "id": row.id,
            "title": "Updated", # title not fetched but not needed for response strictly
            "question_grading": question_grading_dict
        }, None

# ==================== Unified Grading APIs ====================

@router.patch("/{course_id}/assignments/{assignment_id}/grading")
async def update_assignment_grading(course_id: int, assignment_id: int, grading: GradingConfigUpdate):
    """更新作業配分設定 (Unified)"""
    result = await run_in_db_pool(
        _sync_update_content_grading,
        course_id,
        assignment_id,
        grading.include_in_grade,
        grading.weight,
        grading.total_points
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="內容不存在")
        
    logger.info(f"✅ Updated assignment/content grading: ID={result['id']}, Weight={result['weight']}%")
    return result

@router.patch("/{course_id}/exams/{exam_id}/grading")
async def update_exam_grading(course_id: int, exam_id: int, grading: GradingConfigUpdate):
    """更新考試配分設定 (Unified)"""
    # Reuse same logic
    result = await run_in_db_pool(
        _sync_update_content_grading,
        course_id,
        exam_id,
        grading.include_in_grade,
        grading.weight,
        grading.total_points
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="內容不存在")
        
    logger.info(f"✅ Updated exam/content grading: ID={result['id']}, Weight={result['weight']}%")
    return result

@router.patch("/{course_id}/exams/{exam_id}/question-grading")
async def update_exam_question_grading(course_id: int, exam_id: int, question_grading: QuestionGrading):
    """更新考試題目配分 (Unified)"""
    result, error = await run_in_db_pool(
        _sync_update_content_question_grading,
        course_id,
        exam_id,
        question_grading.dict(),
        question_grading.total_points
    )
    
    if error and "不一致" in error:
        raise HTTPException(status_code=400, detail=error)
    elif error:
        raise HTTPException(status_code=404, detail=error)
        
    logger.info(f"✅ Updated question grading for content: ID={result['id']}")
    return result

# ==================== Grading Overview ====================

def _sync_get_grading_overview(course_id: int):
    with engine.connect() as conn:
        # Unified query from course_contents
        query = text("""
            SELECT id, title, content_type, content_subtype, include_in_grade, weight, total_points
            FROM course_contents
            WHERE course_id = :course_id
              AND content_type IN ('assignment', 'exam')
              AND is_visible = true
            ORDER BY created_at DESC
        """)
        result = conn.execute(query, {"course_id": course_id}).fetchall()
        
        assignments = []
        exams = []
        assignment_weight = 0.0
        exam_weight = 0.0
        
        for row in result:
            item = {
                "id": row.id,
                "title": row.title,
                "include_in_grade": row.include_in_grade if row.include_in_grade is not None else False,
                "weight": float(row.weight or 0),
                "total_points": float(row.total_points or 0)
            }
            
            w = item["weight"] if item["include_in_grade"] else 0
            
            # Logic to categorize
            c_type = row.content_type
            c_subtype = row.content_subtype
            
            # Treat 'assignment' type OR 'exam' meant as homework as Assignment category
            if c_type == 'assignment' or (c_type == 'exam' and c_subtype == 'homework'):
                assignments.append(item)
                assignment_weight += w
            else:
                # 'exam' type (quiz, midterm, final, etc.)
                exams.append(item)
                exam_weight += w
                
        total_weight = assignment_weight + exam_weight
        is_valid = abs(total_weight - 100.0) < 0.01
        
        return {
            "course_id": course_id,
            "assignments": assignments,
            "exams": exams,
            "total_weight": total_weight,
            "is_valid": is_valid
        }

@router.get("/{course_id}/grading-overview", response_model=GradingOverviewResponse)
async def get_grading_overview(course_id: int):
    """取得課程配分總覽 (Unified)"""
    result = await run_in_db_pool(_sync_get_grading_overview, course_id)
    return GradingOverviewResponse(**result)


@router.post("/{course_id}/validate-grading")
async def validate_grading(course_id: int):
    """驗證配分設定"""
    overview = await get_grading_overview(course_id)
    
    errors = []
    warnings = []
    
    # 檢查權重總和
    if not overview.is_valid:
        errors.append({
            "type": "weight_sum_invalid",
            "message": f"權重總和應為 100%，目前為 {overview.total_weight}%",
            "expected": 100.0,
            "actual": overview.total_weight
        })
    
    # 檢查是否有項目
    if len(overview.assignments) == 0 and len(overview.exams) == 0:
        warnings.append({
            "type": "no_graded_items",
            "message": "課程尚未設定任何作業或考試"
        })
    
    # 檢查是否有考試
    if len([e for e in overview.exams if (e.get("include_in_grade") or False)]) == 0:
        warnings.append({
            "type": "no_exams",
            "message": "建議至少設定一個計入成績的考試"
        })
    
    return {
        "is_valid": len(errors) == 0,
        "total_weight": overview.total_weight,
        "errors": errors,
        "warnings": warnings
    }
