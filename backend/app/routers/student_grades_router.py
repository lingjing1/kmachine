from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Any
from pydantic import BaseModel
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/student/courses/{course_id}/grades",
    tags=["Student Grades"]
)

# --- Pydantic Models ---

class CourseStaffInfo(BaseModel):
    full_name: str
    email: str
    role: str # 'teacher' or 'ta'

class StudentGradeItem(BaseModel):
    sub_id: Optional[int] = None
    content_id: int
    title: str
    content_type: str
    content_subtype: Optional[str] = None
    total_points: float
    weight: float
    score: Optional[float] = None
    percentage: Optional[float] = None
    grade: Optional[Any] = None
    files: Optional[List[Any]] = None
    submitted_at: Optional[str] = None
    start_time: Optional[str] = None
    is_manual: bool = False

class StudentGradeOverviewResponse(BaseModel):
    course_name: str
    staff: List[CourseStaffInfo]
    grades: List[StudentGradeItem]
    weighted_total: float
    total_scored_weight: float # The sum of weights for assignments that have been scored

# --- API Endpoints ---

@router.get("", response_model=StudentGradeOverviewResponse)
async def get_my_grades(course_id: int, user_id: int = Depends(get_current_user_id)):
    """
    獲取學生個人在特定課程的成績概覽，包含教師資訊、所有計分作業的分數、評語與提交紀錄。
    """
    try:
        def fetch_grade_data():
            with engine.connect() as conn:
                # 1. Get course and teacher info
                course_info = conn.execute(text("""
                    SELECT c.name as course_name, u.full_name, u.email
                    FROM courses c
                    JOIN users u ON c.teacher_id = u.id
                    WHERE c.id = :cid
                """), {"cid": course_id}).fetchone()
                
                if not course_info:
                    return None
                
                # 2. Get TA info
                ta_info = conn.execute(text("""
                    SELECT u.full_name, u.email
                    FROM enrollments e
                    JOIN users u ON e.user_id = u.id
                    WHERE e.course_id = :cid AND e.role = 'ta'
                """), {"cid": course_id}).fetchall()
                
                # 3. Get student's grades and content info
                grades_query = text("""
                    SELECT 
                        cc.id as content_id, cc.title, cc.content_type, cc.content_subtype, 
                        cc.total_points, cc.weight, cc.start_time,
                        COALESCE(sa.id, se.id) as sub_id,
                        COALESCE(sa.score, se.score) as score,
                        -- Both tables now have percentage column
                        COALESCE(sa.percentage, se.percentage, 0) as percentage,
                        COALESCE(sa.grade, se.grade) as grade,
                        sa.files as files,
                        COALESCE(sa.submitted_at, se.submitted_at) as submitted_at,
                        COALESCE(sa.is_manual, se.is_manual, false) as is_manual
                    FROM course_contents cc
                    LEFT JOIN submissions_assignment sa ON (cc.id = sa.content_id AND sa.user_id = :uid)
                    LEFT JOIN submissions_exam se ON (cc.id = se.content_id AND se.user_id = :uid)
                    WHERE cc.course_id = :cid
                    AND (cc.include_in_grade = true OR cc.weight > 0)
                    AND cc.is_visible = true
                    -- 與教師端一致：排除已從章節移除的孤兒內容（unit_id 為 NULL）
                    AND cc.unit_id IS NOT NULL
                    ORDER BY cc.start_time DESC NULLS LAST, cc.created_at DESC
                """)
                grades_rows = conn.execute(grades_query, {"cid": course_id, "uid": user_id}).mappings().all()

                # 4. Get practice records from student_question_logs (similar to teacher side but for 1 student)
                # Map them via knowledge points to course contents
                practice_query = text("""
                    SELECT 
                        cc.id as content_id,
                        COUNT(sql.id) as log_count,
                        AVG(CASE 
                            WHEN sql.correctness = 'correct' THEN 100.0
                            WHEN sql.correctness = 'partial' THEN 90.0
                            WHEN sql.correctness = 'incorrect' THEN 25.0
                            ELSE 0.0
                        END) as avg_percentage,
                        MAX(sql.answered_at) as last_answered_at
                    FROM student_question_logs sql
                    JOIN knowledge_points kp ON sql.knowledge_point_id = kp.id
                    JOIN course_content_knowledge_points cckp ON kp.id = cckp.knowledge_point_id
                    JOIN course_contents cc ON cckp.course_content_id = cc.id
                    WHERE sql.student_id = :uid
                    GROUP BY cc.id
                """)
                practice_logs = conn.execute(practice_query, {"uid": user_id}).mappings().all()
                practice_map = {p['content_id']: p for p in practice_logs}

                # Convert rows to list of dicts to allow mutation
                grades = []
                for row in grades_rows:
                    g = dict(row)
                    cid = g['content_id']
                    
                    # Merge practice log info if missing formal submission
                    if not g['sub_id'] and cid in practice_map:
                        p = practice_map[cid]
                        g['score'] = None # Practice doesn't have score
                        g['percentage'] = float(p['avg_percentage'] or 0)
                        g['submitted_at'] = p['last_answered_at']
                        g['grade'] = {"practice_count": p['log_count']}
                    
                    grades.append(g)
                
                return {
                    "course_name": course_info[0],
                    "teacher": {"full_name": course_info[1], "email": course_info[2], "role": "teacher"},
                    "tas": [{"full_name": r[0], "email": r[1], "role": "助教"} for r in ta_info],
                    "grades": grades
                }

        data = await run_in_db_pool(fetch_grade_data)
        if not data:
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Calculate weighted total
        weighted_total = 0
        total_scored_weight = 0
        
        for g in data['grades']:
            # For practices with logs but no score, we still skip weighted total calculation here 
            # as practices usually have weight 0
            if g['score'] is not None or (g['grade'] and isinstance(g['grade'], dict) and g['grade'].get('practice_count')):
                # 與教師端一致：以 score 為加權依據（score 即 0-100 分數），
                # 僅在缺 score（None 或 0，如 practice 無 score）時退回 percentage。
                score_val = float(g['score']) if g['score'] is not None else None
                pct = float(g['percentage'] or 0)
                effective = score_val if (score_val is not None and score_val != 0) else pct
                w = float(g['weight'] or 0)
                weighted_total += (effective * (w / 100))
                total_scored_weight += w
        
        staff = [CourseStaffInfo(**data['teacher'])]
        for ta in data['tas']:
            staff.append(CourseStaffInfo(**ta))
            
        transformed_grades = []
        for g in data['grades']:
            # Handle potential JSON strings
            import json
            grade_val = g['grade']
            if isinstance(grade_val, str):
                try:
                    grade_val = json.loads(grade_val)
                except:
                    pass
            
            files_val = g['files']
            if isinstance(files_val, str):
                try:
                    files_val = json.loads(files_val)
                except:
                    pass
                    
            transformed_grades.append(StudentGradeItem(
                sub_id=g['sub_id'],
                content_id=g['content_id'],
                title=g['title'],
                content_type=g['content_type'],
                content_subtype=g['content_subtype'],
                total_points=float(g['total_points'] or 0),
                weight=float(g['weight'] or 0),
                score=float(g['score']) if g['score'] is not None else None,
                percentage=float(g['percentage'] or 0),
                grade=grade_val,
                files=files_val,
                submitted_at=str(g['submitted_at']) if g['submitted_at'] else None,
                start_time=str(g['start_time']) if g['start_time'] else None,
                is_manual=g['is_manual']
            ))
            
        return StudentGradeOverviewResponse(
            course_name=data['course_name'],
            staff=staff,
            grades=transformed_grades,
            weighted_total=round(weighted_total, 2),
            total_scored_weight=round(total_scored_weight, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching student grades: {e}")
        raise HTTPException(status_code=500, detail=str(e))
