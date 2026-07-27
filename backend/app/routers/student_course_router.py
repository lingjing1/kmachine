"""
Student Course Router
處理學生端課程相關的 API，包含：
- 課程列表
- 課程詳情
- 課程公告
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.concurrency import run_in_db_pool
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/student",
    tags=["Student Courses"]
)

# ==================== Schemas ====================

class AnnouncementAttachmentItem(BaseModel):
    """公告附件項目"""
    id: int
    original_file_name: str
    file_type: str
    file_size_bytes: int
    download_url: str

class AnnouncementResponse(BaseModel):
    """公告回應 (學生版)"""
    id: int
    title: str
    content: str
    is_pinned: bool
    is_visible: bool
    created_at: str
    author_name: str
    course_name: Optional[str] = None
    course_id: Optional[int] = None
    updated_at: Optional[str] = None
    attachments: List[AnnouncementAttachmentItem] = []

class CourseResponse(BaseModel):
    """學生課程回應"""
    id: int
    name: str
    semester: str
    description: Optional[str] = None
    teacher_name: str
    enrollment_role: str = 'student'  # 'student' or 'ta'

# ==================== Endpoints ====================

def _sync_get_student_courses(student_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name, e.role as role
            FROM enrollments e
            JOIN courses c ON e.course_id = c.id
            LEFT JOIN users u ON c.teacher_id = u.id
            WHERE e.user_id = :student_id
            
            UNION DISTINCT
            
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name, 'teacher' as role
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            WHERE c.teacher_id = :student_id
            
            ORDER BY id DESC
        """)
        result = conn.execute(query, {"student_id": student_id})
        
        courses = []
        for row in result:
            courses.append({
                "id": row.id,
                "name": row.name,
                "semester": row.semester_name,
                "description": row.description,
                "teacher_name": row.teacher_name or "未知教師",
                "enrollment_role": row.role,
            })
        return courses

@router.get("/courses", response_model=List[CourseResponse])
async def get_student_courses(
    student_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 user_id
):
    """
    取得學生已選修的課程列表
    """
    courses_data = await run_in_db_pool(_sync_get_student_courses, student_id)
    return [CourseResponse(**c) for c in courses_data]

def _sync_fetch_announcement_attachments(conn, announcement_ids: list) -> dict:
    """批次查詢公告附件，回傳 {announcement_id: [attachments]} 的字典"""
    if not announcement_ids:
        return {}
    att_query = text("""
        SELECT id, attachable_id, original_file_name, file_type, file_size_bytes, uploaded_at
        FROM attachments
        WHERE attachable_type = 'announcement'
        AND attachable_id IN :ids
    """)
    att_rows = conn.execute(att_query, {"ids": tuple(announcement_ids)}).fetchall()
    result = {}
    for row in att_rows:
        aid = row.attachable_id
        if aid not in result:
            result[aid] = []
        result[aid].append({
            "id": row.id,
            "original_file_name": row.original_file_name,
            "file_type": row.file_type or "",
            "file_size_bytes": row.file_size_bytes or 0,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else "",
            "download_url": f"/api/attachments/{row.id}/download"
        })
    return result

def _sync_get_all_student_announcements(student_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT 
                a.id, a.title, a.content, a.is_pinned, a.is_visible, a.created_at, a.updated_at,
                u.full_name as author_name,
                c.name as course_name,
                c.id as course_id
            FROM course_announcements a
            JOIN courses c ON a.course_id = c.id
            LEFT JOIN enrollments e ON e.course_id = c.id AND e.user_id = :user_id
            LEFT JOIN users u ON a.author_id = u.id
            WHERE (
                (e.user_id IS NOT NULL AND a.is_visible = TRUE) 
                OR (e.role = 'ta') 
                OR (c.teacher_id = :user_id)
            )
            ORDER BY a.is_pinned DESC, a.updated_at DESC
            LIMIT 50
        """)
        result = conn.execute(query, {"user_id": student_id})
        
        announcements = []
        for row in result:
            announcements.append({
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "is_pinned": row.is_pinned,
                "is_visible": row.is_visible,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "author_name": row.author_name or "未知",
                "course_name": row.course_name,
                "course_id": row.course_id,
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
                "attachments": []
            })
        
        # 批次查詢附件
        if announcements:
            ann_ids = [a["id"] for a in announcements]
            att_map = _sync_fetch_announcement_attachments(conn, ann_ids)
            for a in announcements:
                a["attachments"] = att_map.get(a["id"], [])
        
        return announcements

@router.get("/announcements", response_model=List[AnnouncementResponse])
async def get_all_student_announcements(
    student_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 user_id
):
    """
    取得該學生所有修習課程的最新公告 (跨課程)
    """
    announcements_data = await run_in_db_pool(_sync_get_all_student_announcements, student_id)
    return [AnnouncementResponse(**a) for a in announcements_data]

def _sync_get_course_announcements(course_id: int, user_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT 
                a.id, a.title, a.content, a.is_pinned, a.is_visible, a.created_at, a.updated_at,
                u.full_name as author_name,
                c.name as course_name
            FROM course_announcements a
            JOIN courses c ON a.course_id = c.id
            LEFT JOIN users u ON a.author_id = u.id
            WHERE a.course_id = :course_id 
              AND (
                  a.is_visible = TRUE 
                  OR c.teacher_id = :user_id 
                  OR EXISTS (
                      SELECT 1 FROM enrollments WHERE course_id = :course_id AND user_id = :user_id AND role = 'ta'
                  )
              )
            ORDER BY a.is_pinned DESC, a.updated_at DESC
        """)
        result = conn.execute(query, {"course_id": course_id, "user_id": user_id})
        
        announcements = []
        for row in result:
            announcements.append({
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "is_pinned": row.is_pinned,
                "is_visible": row.is_visible,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "author_name": row.author_name or "未知",
                "course_name": row.course_name,
                "course_id": course_id,
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
                "attachments": []
            })
        
        # 批次查詢附件
        if announcements:
            ann_ids = [a["id"] for a in announcements]
            att_map = _sync_fetch_announcement_attachments(conn, ann_ids)
            for a in announcements:
                a["attachments"] = att_map.get(a["id"], [])
        
        return announcements

@router.get("/courses/{course_id}/announcements", response_model=List[AnnouncementResponse])
async def get_course_announcements(
    course_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """
    取得特定課程的所有公告
    """
    announcements_data = await run_in_db_pool(_sync_get_course_announcements, course_id, user_id)
    return [AnnouncementResponse(**a) for a in announcements_data]

# ==================== Join Course Endpoint ====================

class JoinCourseRequest(BaseModel):
    """加入課程請求"""
    enrollment_code: str

class JoinCourseResponse(BaseModel):
    """加入課程回應"""
    course_id: int
    course_name: str
    message: str
def _sync_join_course(student_id: int, code: str):
    with engine.connect() as conn:
        # 1. 查詢課程
        course_query = text("""
            SELECT id, name, enrollment_code_expires_at
            FROM courses
            WHERE enrollment_code = :code
        """)
        course = conn.execute(course_query, {"code": code}).fetchone()
        
        if not course:
            return None, "Invalid code"
        
        course_id, course_name, expires_at = course
        
        # 2. 檢查代碼是否過期
        now = get_now_taipei()
        if expires_at and expires_at.tzinfo:
            now = now.astimezone(expires_at.tzinfo)
        
        if not expires_at or now > expires_at:
            return None, "Expired code"
        
        # 3. 檢查是否已加入
        enrollment_check = conn.execute(
            text("SELECT 1 FROM enrollments WHERE user_id = :user_id AND course_id = :course_id"),
            {"user_id": student_id, "course_id": course_id}
        ).fetchone()
        
        if enrollment_check:
            return None, "Already joined"
        
        insert_query = text("""
            INSERT INTO enrollments (user_id, course_id, enrolled_at, enrollment_method)
            VALUES (:user_id, :course_id, :now, 'student_code')
        """)
        conn.execute(insert_query, {
            "user_id": student_id,
            "course_id": course_id,
            "now": get_now_taipei()
        })
        conn.commit()
        
        return {
            "course_id": course_id,
            "course_name": course_name,
            "message": "成功加入課程"
        }, None

@router.post("/courses/join", response_model=JoinCourseResponse)
async def join_course(
    request: JoinCourseRequest,
    student_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 user_id
):
    """
    學生使用課程代碼加入課程
    """
    import traceback
    
    try:
        code = request.enrollment_code.upper().strip()
        # ✅ Phase 3: student_id 已從 JWT 自動提取
        
        if len(code) != 8:
            raise HTTPException(status_code=400, detail="課程代碼格式錯誤（應為 8 位）")
        
        result, error = await run_in_db_pool(_sync_join_course, student_id, code)
        
        if error == "Invalid code":
            raise HTTPException(status_code=404, detail="課程代碼無效")
        elif error == "Expired code":
            raise HTTPException(status_code=400, detail="課程代碼已過期")
        elif error == "Already joined":
            raise HTTPException(status_code=409, detail="您已加入此課程")
        elif error:
             raise HTTPException(status_code=500, detail=f"Internal Error: {error}")
             
        return JoinCourseResponse(**result)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in join_course: {e}") 
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}")
