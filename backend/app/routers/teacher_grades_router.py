from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy import text
import json
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---

class SubmissionInfo(BaseModel):
    id: Optional[int] = None
    content_id: int
    content_title: str
    content_type: str
    content_subtype: Optional[str] = None
    total_points: float
    weight: float
    score: Optional[float] = None
    percentage: Optional[float] = None
    grade: Optional[Any] = None
    files: Optional[List[Any]] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_manual: bool = False

class StudentGradeInfo(BaseModel):
    user_id: int
    full_name: str
    email: str
    student_id: Optional[str] = None  # From student_profiles (學號)
    major: Optional[str] = None       # From student_profiles (科系)
    role: Optional[str] = None        # 'student' or 'ta'
    submissions: List[SubmissionInfo]
    weighted_score: float             # Total weighted score (0-100)
    total_percentage: float           # Same as weighted score for now

class ContentInfo(BaseModel):
    content_id: int
    title: str
    content_type: str
    content_subtype: Optional[str] = None
    total_points: float
    weight: float
    include_in_grade: bool
    avg_score: Optional[float] = None
    avg_percentage: Optional[float] = None
    submission_count: int
    total_students: int

class GradeOverviewResponse(BaseModel):
    students: List[StudentGradeInfo]
    contents: List[ContentInfo]
    total_weight: float
    weight_valid: bool

class WeightUpdateItem(BaseModel):
    content_id: int
    weight: float

class WeightUpdateRequest(BaseModel):
    weights: List[WeightUpdateItem]

class UpdateSubmissionGradeRequest(BaseModel):
    content_id: int
    user_id: int
    score: float
    grade: Any  # Can be List of question details or a general feedback object

# --- API Endpoints ---

@router.get("/api/teacher/courses/{course_id}/grades", response_model=GradeOverviewResponse)
async def get_course_grades(
    course_id: int,
    include_practice: bool = Query(False, description="是否包含不計分的練習內容"),
    teacher_id: int = Depends(get_current_user_id)
):
    """
    獲取課程成績總覽，包含所有學生的作答紀錄和加權成績。
    """
    try:
        # 1. Get all students enrolled in the course and course contents info
        # Using raw SQL for complex join and aggregation
        
        # Query 1: Get students and TAs in the course
        students_query = text("""
            SELECT 
                u.id as user_id, 
                u.full_name, 
                u.email,
                sp.student_id,
                sp.major,
                ce.role as enrollment_role
            FROM users u
            JOIN enrollments ce ON u.id = ce.user_id
            LEFT JOIN student_profiles sp ON u.id = sp.user_id
            WHERE ce.course_id = :course_id 
            AND ce.role IN ('student', 'ta')
            ORDER BY (CASE WHEN ce.role = 'ta' THEN 1 ELSE 0 END) ASC, sp.student_id, u.full_name
        """)
        
        contents_query = text("""
            SELECT 
                cc.id, cc.title, cc.content_type, cc.content_subtype, 
                cc.total_points, cc.weight, cc.include_in_grade
            FROM course_contents cc
            LEFT JOIN course_units cu ON cc.unit_id = cu.id
            WHERE cc.course_id = :course_id
            AND (cc.include_in_grade = true OR cc.content_type = 'exam' OR (:include_practice = true AND cc.is_visible = true))
            AND cc.is_visible = true
            -- 排除已從章節移除的孤兒內容（刪除按鈕只將 unit_id 設為 NULL，
            -- 課程頁因按章節分組而隱藏，成績頁需一致排除，否則孤兒內容會重新出現成一欄）
            AND cc.unit_id IS NOT NULL
            ORDER BY cu.topic_id ASC NULLS LAST, cc.display_order ASC, cc.created_at ASC
        """)

        # Run queries in parallel via db pool
        def fetch_data():
            with engine.connect() as conn:
                students = conn.execute(students_query, {"course_id": course_id}).mappings().all()
                contents = conn.execute(contents_query, {"course_id": course_id, "include_practice": include_practice}).mappings().all()
                return students, contents

        students_data, contents_data = await run_in_db_pool(fetch_data)
        
        if not students_data:
            return GradeOverviewResponse(
                students=[], 
                contents=[], 
                total_weight=0, 
                weight_valid=True
            )

        # Map content info for easy lookup
        content_map = {c['id']: dict(c) for c in contents_data}
        content_ids = [c['id'] for c in contents_data]
        
        if not content_ids:
             return GradeOverviewResponse(
                students=[
                    StudentGradeInfo(
                        user_id=s['user_id'],
                        full_name=s['full_name'],
                        email=s['email'],
                        student_id=s['student_id'],
                        major=s['major'],
                        role=s.get('enrollment_role'),
                        submissions=[],
                        weighted_score=0,
                        total_percentage=0
                    ) for s in students_data
                ], 
                contents=[], 
                total_weight=0, 
                weight_valid=True
            )

        # Query 3: Get all submissions for these students and contents
        submissions_query = text("""
            SELECT 
                u.id as user_id,
                cc.id as content_id,
                COALESCE(sa.id, se.id) as sub_id,
                
                -- Score handling
                COALESCE(sa.score, se.score) as score,
                
                -- Percentage handling (both tables now have percentage)
                COALESCE(sa.percentage, se.percentage, 0) as percentage,
                
                -- Timestamps
                COALESCE(sa.submitted_at, se.submitted_at) as submitted_at,
                COALESCE(sa.updated_at, se.updated_at) as updated_at,
                
                -- Grade/Feedback json
                COALESCE(sa.grade, se.grade) as grade,
                
                -- Files for upload assignments
                sa.files as files,
                
                -- Manual review flag
                COALESCE(sa.is_manual, se.is_manual, false) as is_manual
                
            FROM users u
            CROSS JOIN course_contents cc
            LEFT JOIN submissions_assignment sa 
                ON sa.user_id = u.id AND sa.content_id = cc.id
            LEFT JOIN submissions_exam se 
                ON se.user_id = u.id AND se.content_id = cc.id
            WHERE u.id IN :user_ids
            AND cc.id IN :content_ids
        """)

        # Query 4: Get practice records from student_question_logs if include_practice is true
        # We need to map which unit/KP the content belongs to. 
        # For simplicity, we'll fetch all logs for this course's students.
        practice_logs_query = text("""
            SELECT 
                sql.student_id as user_id,
                cc.id as content_id,
                
                -- Aggregate detailed logs into JSON
                JSON_AGG(JSON_BUILD_OBJECT(
                    'question_text', COALESCE(qb.question_data->>'question', qb.question_data->>'question_text', '未知問題'),
                    'student_answer', sql.answer->>'text',
                    'correct_answer', qb.question_data->>'solution',
                    'correctness', 
                        CASE 
                            WHEN sql.correctness = 'correct' THEN 'correct'
                            WHEN sql.correctness = 'incorrect' THEN 'incorrect'
                            ELSE 'partial'
                        END,
                    'feedback', sql.feedback,
                    'question_type', qb.question_type,
                    'answered_at', sql.answered_at
                ) ORDER BY sql.answered_at DESC) as details,
                
                AVG(CASE 
                    WHEN sql.correctness = 'correct' THEN 100.0
                    WHEN sql.correctness = 'partial' THEN 90.0
                    WHEN sql.correctness = 'incorrect' THEN 25.0
                    ELSE 0.0
                END) as avg_percentage,
                COUNT(sql.id) as log_count,
                MAX(sql.answered_at) as last_answered_at
            FROM student_question_logs sql
            JOIN question_bank qb ON sql.question_id = qb.id
            JOIN knowledge_points kp ON sql.knowledge_point_id = kp.id
            JOIN course_content_knowledge_points cckp ON kp.id = cckp.knowledge_point_id
            JOIN course_contents cc ON cckp.course_content_id = cc.id
            WHERE sql.student_id IN :user_ids
              AND cc.id IN :content_ids
            GROUP BY sql.student_id, cc.id
        """)

        user_ids = [s['user_id'] for s in students_data]
        
        def fetch_all_data():
             with engine.connect() as conn:
                submissions = conn.execute(
                    submissions_query, 
                    {"user_ids": tuple(user_ids), "content_ids": tuple(content_ids)}
                ).mappings().all()
                
                practice_logs = []
                if include_practice:
                    practice_logs = conn.execute(
                        practice_logs_query,
                        {"user_ids": tuple(user_ids), "content_ids": tuple(content_ids)}
                    ).mappings().all()
                
                return submissions, practice_logs
        
        submissions_data, practice_logs_data = await run_in_db_pool(fetch_all_data)

        # Process data
        student_submissions = {} # user_id -> {content_id -> submission_dict}
        
        # Build Stats
        content_stats = {cid: {'total_score': 0, 'total_percentage': 0, 'count': 0} for cid in content_ids}

        for sub_row in submissions_data:
            # Convert RowMapping to mutable dict
            sub = dict(sub_row)
            uid = sub['user_id']
            cid = sub['content_id']
            if uid not in student_submissions: student_submissions[uid] = {}
            
            # Only store if actually submitted (use sub_id as it is more reliable than submitted_at)
            if sub.get('sub_id') is not None:
                student_submissions[uid][cid] = sub
            
                if sub['score'] is not None:
                    content_stats[cid]['total_score'] += float(sub['score'])
                    content_stats[cid]['total_percentage'] += float(sub['percentage'] or 0)
                    content_stats[cid]['count'] += 1
        
        # Merge practice logs into student_submissions

        for log_row in practice_logs_data:
            log = dict(log_row)
            uid = log['user_id']
            cid = log['content_id']
            if uid not in student_submissions: student_submissions[uid] = {}
            
            existing = student_submissions[uid].get(cid)
            
            # Create practice details object
            practice_grade = {
                'practice_count': log['log_count'],
                'details': log['details']
            }

            if not existing:
                # No existing submission, create one from logs
                student_submissions[uid][cid] = {
                    'score': None,
                    'percentage': float(log['avg_percentage'] or 100.0),
                    'submitted_at': log['last_answered_at'],
                    'updated_at': log['last_answered_at'],
                    'grade': practice_grade,
                    'sub_id': None,
                    'files': None,
                    'is_manual': False
                }
            else:
                # Merge into existing submission
                # Use practice percentage only if current score/percentage is missing
                if existing.get('score') is None and (existing.get('percentage') is None or existing.get('percentage') == 0):
                    existing['percentage'] = float(log['avg_percentage'] or 100.0)
                    if not existing.get('submitted_at'):
                        existing['submitted_at'] = log['last_answered_at']
                
                # Attach practice details
                if isinstance(existing.get('grade'), dict):
                    existing['grade'].update(practice_grade)
                else:
                    existing['grade'] = practice_grade
            
            if cid in content_stats:
                content_stats[cid]['count'] += 1

        # Calculate Content Info with stats
        final_contents = []
        total_weight = 0
        for c in contents_data:
            cid = c['id']
            stats = content_stats.get(cid, {'count': 0})
            count = stats.get('count', 0)
            
            total_score_val = stats.get('total_score', 0)
            total_percentage_val = stats.get('total_percentage', 0)
            
            avg_score = total_score_val / count if count > 0 else 0
            avg_percentage = total_percentage_val / count if count > 0 else 0
            
            current_weight = float(c['weight'] or 0)
            total_weight += current_weight
            
            final_contents.append(ContentInfo(
                content_id=cid,
                title=c['title'],
                content_type=c['content_type'],
                content_subtype=c['content_subtype'],
                total_points=float(c['total_points'] or 100),
                weight=current_weight,
                include_in_grade=c['include_in_grade'],
                avg_score=round(avg_score, 2) if count > 0 else None,
                avg_percentage=round(avg_percentage, 2) if count > 0 else None,
                submission_count=count,
                total_students=len(students_data)
            ))
        
        # Build Student Info
        final_students = []
        for s in students_data:
            uid = s['user_id']
            user_subs = []
            weighted_total = 0
            
            for c in contents_data:
                cid = c['id']
                sub_data = student_submissions.get(uid, {}).get(cid)
                
                score = None
                percentage = None
                grade = None
                submitted_at = None
                updated_at = None
                files = None
                sub_id = None
                is_manual = False
                
                if sub_data:
                    score = float(sub_data['score']) if sub_data['score'] is not None else None
                    percentage = float(sub_data['percentage'] or 0)
                    grade = sub_data['grade']
                    files = sub_data.get('files')
                    sub_id = sub_data.get('sub_id')
                    is_manual = sub_data.get('is_manual') or False
                    
                    # Explicitly parse JSON strings if needed
                    if isinstance(grade, str):
                        try:
                            grade = json.loads(grade)
                        except:
                            pass
                    
                    if isinstance(files, str):
                        try:
                            files = json.loads(files)
                        except:
                            pass
                    
                    if grade:
                        questions = []
                        if isinstance(grade, list):
                            questions = grade
                        elif isinstance(grade, dict):
                            questions = grade.get('questions', grade.get('details', []))
                        
                        if isinstance(questions, list) and len(questions) > 0:
                            total_p = 0
                            valid_qs = 0
                            for i, q in enumerate(questions):
                                # Ensure q is a mutable dict (RowMapping is immutable)
                                if not isinstance(q, dict) and hasattr(q, '_asdict'):
                                    q = dict(q._asdict())
                                elif not isinstance(q, dict):
                                    q = dict(q)
                                
                                # Put it back into the list to ensure the mutations persist
                                questions[i] = q
                                
                                raw_corr = str(q.get('correctness') or '').lower()
                                # Normalize label for frontend and calculate score
                                if raw_corr in ['correct', 'true', 'right']:
                                    q['correctness'] = 'correct'
                                    total_p += 100
                                    valid_qs += 1
                                elif raw_corr in ['partial', 'partially_correct', 'partially']:
                                    q['correctness'] = 'partial'
                                    total_p += 90
                                    valid_qs += 1
                                elif raw_corr in ['incorrect', 'false', 'wrong']:
                                    q['correctness'] = 'incorrect'
                                    total_p += 25
                                    valid_qs += 1
                                elif q.get('student_answer'):
                                    # If has answer but unknown label, default to partial/incorrect (gray fix)
                                    q['correctness'] = 'partial'
                                    total_p += 25 
                                    valid_qs += 1
                            
                            # Only overwrite percentage if score is missing or 0
                            if (score is None or score == 0) and valid_qs > 0:
                                percentage = total_p / valid_qs

                    if sub_data['submitted_at']:
                        submitted_at = sub_data['submitted_at'].isoformat() if not isinstance(sub_data['submitted_at'], str) else sub_data['submitted_at']
                    if sub_data['updated_at']:
                        updated_at = sub_data['updated_at'].isoformat() if not isinstance(sub_data['updated_at'], str) else sub_data['updated_at']
                    
                    weight = float(c['weight'] or 0)
                    # 以 score 為加權依據（score 即 0-100 分數；total_points 一律 100）。
                    # 部分繳交路徑（如檔案批改）只寫入 score 未寫 percentage，
                    # 故 score 為主、僅在缺 score（None 或 0）時退回 percentage。
                    # 條件與前端格子顯示一致，確保「總分 = 各格顯示值的加權和」。
                    effective = score if (score is not None and score != 0) else (percentage or 0)
                    weighted_total += effective * (weight / 100)

                user_subs.append(SubmissionInfo(
                    content_id=cid,
                    content_title=c['title'],
                    content_type=c['content_type'],
                    content_subtype=c['content_subtype'],
                    total_points=float(c['total_points'] or 100),
                    weight=float(c['weight'] or 0),
                    score=score,
                    percentage=percentage,
                    grade=grade,
                    is_manual=is_manual,
                    files=files,
                    id=sub_id,
                    submitted_at=submitted_at,
                    updated_at=updated_at
                ))
            
            final_students.append(StudentGradeInfo(
                user_id=uid,
                full_name=s['full_name'],
                email=s['email'],
                student_id=s['student_id'],
                major=s['major'],
                role=s.get('enrollment_role'),
                submissions=user_subs,
                weighted_score=round(weighted_total, 2),
                total_percentage=round(weighted_total, 2)
            ))
            
        return GradeOverviewResponse(
            students=final_students,
            contents=final_contents,
            total_weight=round(total_weight, 2),
            weight_valid=abs(total_weight - 100) < 0.01  # Allow small float error
        )

    except Exception as e:
        logger.error(f"Error fetching grades for course {course_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/teacher/courses/{course_id}/grades/weights")
async def update_grade_weights(
    course_id: int,
    request: WeightUpdateRequest,
    teacher_id: int = Depends(get_current_user_id)
):
    """
    更新課程評分權重
    """
    try:
        # Validate total weight
        total_weight = sum(item.weight for item in request.weights)
        # if abs(total_weight - 100) > 0.01:
        #     raise HTTPException(status_code=400, detail=f"總權重必須為 100%，目前為 {total_weight}%")

        update_query = text("""
            UPDATE course_contents
            SET weight = :weight
            WHERE id = :content_id 
            AND course_id = :course_id
        """)
        
        def execute_updates():
            with engine.begin() as conn: # Use transaction
                for item in request.weights:
                    result = conn.execute(
                        update_query, 
                        {"weight": item.weight, "content_id": item.content_id, "course_id": course_id}
                    )
        
        await run_in_db_pool(execute_updates)
        
        return {"status": "success", "message": "Weights updated successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating weights for course {course_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.put("/api/teacher/courses/{course_id}/grades/submissions")
async def update_submission_grade(
    course_id: int,
    request: UpdateSubmissionGradeRequest,
    teacher_id: int = Depends(get_current_user_id)
):
    """
    手動修改學生的成績和評語
    """
    try:
        # 1. Determine which table to update based on content_subtype
        check_query = text("SELECT content_subtype, total_points FROM course_contents WHERE id = :cid")
        
        def execute_update():
            with engine.begin() as conn:
                row = conn.execute(check_query, {"cid": request.content_id}).fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Content not found")
                
                subtype, total_points = row
                total_points = float(total_points or 100)
                percentage = (request.score / total_points * 100) if total_points > 0 else request.score
                
                # CONTENT_TYPE determines the table, not just subtype
                # But here we rely on subtype for exams
                if subtype == 'exam':
                    table_name = "submissions_exam"
                    # Include percentage for exams
                    upsert_query = text(f"""
                        INSERT INTO {table_name} (user_id, content_id, score, percentage, grade, updated_at, submitted_at, is_manual)
                        VALUES (:user_id, :content_id, :score, :percentage, CAST(:grade AS json), :now, :now, true)
                        ON CONFLICT (user_id, content_id) DO UPDATE SET
                            score = EXCLUDED.score,
                            percentage = EXCLUDED.percentage,
                            grade = EXCLUDED.grade,
                            updated_at = EXCLUDED.updated_at,
                            is_manual = true
                    """)
                else:
                    table_name = "submissions_assignment"
                    # Assignments now also have 'percentage' column
                    upsert_query = text(f"""
                        INSERT INTO {table_name} (user_id, content_id, score, percentage, grade, updated_at, submitted_at, is_manual)
                        VALUES (:user_id, :content_id, :score, :percentage, CAST(:grade AS json), :now, :now, true)
                        ON CONFLICT (user_id, content_id) DO UPDATE SET
                            score = EXCLUDED.score,
                            percentage = EXCLUDED.percentage,
                            grade = EXCLUDED.grade,
                            updated_at = EXCLUDED.updated_at,
                            is_manual = true
                    """)
                
                from backend.app.utils.time_utils import get_now_taipei
                conn.execute(upsert_query, {
                    "score": request.score,
                    "percentage": percentage,
                    "grade": json.dumps(request.grade),
                    "content_id": request.content_id,
                    "user_id": request.user_id,
                    "now": get_now_taipei()
                })
        
        await run_in_db_pool(execute_update)
        return {"status": "success", "message": "Grade updated successfully"}

    except Exception as e:
        logger.error(f"Error updating grade for student {request.user_id} in course {course_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
