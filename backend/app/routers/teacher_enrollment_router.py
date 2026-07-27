"""
Enrollment Code Endpoints for Teachers
產生和查看課程加入代碼，以及課程助教管理
"""
import secrets
import string
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import (
    get_current_user_id,
    check_teacher_or_course_ta,
    require_teacher,
    security,
    verify_token,
)

router = APIRouter()
logger = logging.getLogger(__name__)

class EnrollmentCodeResponse(BaseModel):
    """課程代碼回應"""
    enrollment_code: str
    expires_at: str
    is_expired: bool

def generate_enrollment_code() -> str:
    """產生 8 位大寫字母+數字代碼"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

def _sync_generate_enrollment_code(course_id: int):
    with engine.connect() as conn:
        # 1. 檢查課程是否存在
        course_check = conn.execute(
            text("SELECT id, teacher_id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return None, "課程不存在"
        
        # 2. 產生唯一代碼
        code = None
        for _ in range(10):
            candidate = generate_enrollment_code()
            # 檢查唯一性
            existing = conn.execute(
                text("SELECT id FROM courses WHERE enrollment_code = :code AND id != :course_id"),
                {"code": candidate, "course_id": course_id}
            ).fetchone()
            
            if not existing:
                code = candidate
                break
        
        if not code:
            return None, "無法產生課程加入代碼，請稍後再試"
        
        # 3. 設定 30 天有效期
        expires_at = get_now_taipei() + timedelta(days=30)
        
        # 4. 更新課程表
        update_query = text("""
            UPDATE courses 
            SET enrollment_code = :code, 
                enrollment_code_expires_at = :expires_at
            WHERE id = :course_id
            RETURNING enrollment_code, enrollment_code_expires_at
        """)
        result = conn.execute(update_query, {
            "code": code,
            "expires_at": expires_at,
            "course_id": course_id
        })
        conn.commit()
        row = result.fetchone()
        
        return (row[0], row[1]), None

@router.post("/api/teacher/courses/{course_id}/enrollment-code", response_model=EnrollmentCodeResponse, tags=["Teachers"])
async def generate_course_enrollment_code(course_id: int):
    """
    產生或重新產生課程加入代碼
    """
    result, error = await run_in_db_pool(_sync_generate_enrollment_code, course_id)
    
    if error == "Course not found":
        raise HTTPException(status_code=404, detail="課程不存在")
    elif error:
        raise HTTPException(status_code=500, detail="無法產生唯一代碼，請稍後再試")
        
    code, expires_at = result
    logger.info(f"✅ Generated enrollment code for course {course_id}: {code}")
    
    return EnrollmentCodeResponse(
        enrollment_code=code,
        expires_at=expires_at.isoformat(),
        is_expired=False
    )

def _sync_get_enrollment_code(course_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT c.enrollment_code, c.enrollment_code_expires_at, c.teacher_id
            FROM courses c
            WHERE c.id = :course_id
        """)
        result = conn.execute(query, {"course_id": course_id}).fetchone()
        
        if not result:
            return None
            
        return (result.enrollment_code, result.enrollment_code_expires_at, result.teacher_id)

@router.get("/api/teacher/courses/{course_id}/enrollment-code", response_model=EnrollmentCodeResponse, tags=["Teachers"])
async def get_course_enrollment_code(course_id: int):
    """
    查看課程當前的加入代碼
    """
    result = await run_in_db_pool(_sync_get_enrollment_code, course_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="課程不存在")
        
    code, expires_at, _ = result
    
    if not code:
        raise HTTPException(status_code=404, detail="課程尚未產生加入代碼")
        
    now = get_now_taipei()
    if expires_at and expires_at.tzinfo:
        now = now.astimezone(expires_at.tzinfo)
        
    is_expired = now > expires_at if expires_at else True
    
    return EnrollmentCodeResponse(
        enrollment_code=code,
        expires_at=expires_at.isoformat() if expires_at else "",
        is_expired=is_expired
    )


# ============================================================
# TA Management Endpoints
# ============================================================

class CourseMemberResponse(BaseModel):
    """課程成員資訊"""
    user_id: int
    full_name: str
    email: str
    student_id: Optional[str] = None
    department: Optional[str] = None
    enrollment_role: str  # 'student' or 'ta'
    enrolled_at: str


def _sync_get_course_members(course_id: int, teacher_id: int):
    with engine.connect() as conn:
        # Verify requester is teacher or TA of the course
        check_teacher_or_course_ta(teacher_id, course_id, conn)

        rows = conn.execute(
            text("""
                SELECT u.id, u.full_name, u.email,
                       sp.student_id, sp.major,
                       e.role AS enrollment_role, e.enrolled_at
                FROM enrollments e
                JOIN users u ON e.user_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE e.course_id = :course_id
                ORDER BY e.enrolled_at ASC
            """),
            {"course_id": course_id}
        ).fetchall()

        return [
            {
                "user_id": row.id,
                "full_name": row.full_name,
                "email": row.email,
                "student_id": row.student_id,
                "department": row.major,
                "enrollment_role": row.enrollment_role,
                "enrolled_at": row.enrolled_at.isoformat() if row.enrolled_at else "",
            }
            for row in rows
        ]


@router.get(
    "/api/teacher/courses/{course_id}/members",
    response_model=List[CourseMemberResponse],
    tags=["Teachers"]
)
async def list_course_members(
    course_id: int,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    列出課程所有成員（含助教標記）。
    教師或該課程助教可呼叫。
    """
    payload = verify_token(credentials)
    user_id = payload.get("user_id")
    members = await run_in_db_pool(_sync_get_course_members, course_id, user_id)
    return members


def _sync_promote_ta(course_id: int, teacher_id: int, target_user_id: int):
    with engine.connect() as conn:
        # Only the course teacher or an admin can promote
        is_teacher_or_admin = conn.execute(
            text("""
                SELECT 1 FROM courses c
                JOIN users u ON u.id = :uid
                JOIN roles r ON u.role_id = r.id
                WHERE c.id = :cid AND (c.teacher_id = :uid OR r.name = 'admin')
            """),
            {"cid": course_id, "uid": teacher_id}
        ).fetchone()
        if not is_teacher_or_admin:
            raise HTTPException(status_code=403, detail="只有授課教師或管理員可以指定助教")

        enrollment = conn.execute(
            text("SELECT role FROM enrollments WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        ).fetchone()

        if not enrollment:
            raise HTTPException(status_code=404, detail="該使用者尚未加入此課程")

        if enrollment.role == 'ta':
            return {"message": "該使用者已經是助教"}

        conn.execute(
            text("UPDATE enrollments SET role = 'ta' WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        )
        conn.commit()
        return {"message": "已成功升為助教"}


@router.patch(
    "/api/teacher/courses/{course_id}/members/{target_user_id}/promote-ta",
    tags=["Teachers"]
)
async def promote_to_ta(
    course_id: int,
    target_user_id: int,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    將課程成員升為助教。僅授課教師可呼叫。
    """
    payload = verify_token(credentials)
    teacher_id = payload.get("user_id")
    result = await run_in_db_pool(_sync_promote_ta, course_id, teacher_id, target_user_id)
    logger.info(f"Teacher {teacher_id} promoted user {target_user_id} to TA in course {course_id}")
    return result


def _sync_demote_student(course_id: int, teacher_id: int, target_user_id: int):
    with engine.connect() as conn:
        # Only the course teacher or an admin can demote
        is_teacher_or_admin = conn.execute(
            text("""
                SELECT 1 FROM courses c
                JOIN users u ON u.id = :uid
                JOIN roles r ON u.role_id = r.id
                WHERE c.id = :cid AND (c.teacher_id = :uid OR r.name = 'admin')
            """),
            {"cid": course_id, "uid": teacher_id}
        ).fetchone()
        if not is_teacher_or_admin:
            raise HTTPException(status_code=403, detail="只有授課教師或管理員可以變更助教身份")

        enrollment = conn.execute(
            text("SELECT role FROM enrollments WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        ).fetchone()

        if not enrollment:
            raise HTTPException(status_code=404, detail="該使用者尚未加入此課程")

        if enrollment.role == 'student':
            return {"message": "該使用者已經是學生身份"}

        conn.execute(
            text("UPDATE enrollments SET role = 'student' WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        )
        conn.commit()
        return {"message": "已成功降為學生"}


@router.patch(
    "/api/teacher/courses/{course_id}/members/{target_user_id}/demote-student",
    tags=["Teachers"]
)
async def demote_to_student(
    course_id: int,
    target_user_id: int,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    將課程助教降回學生身份。僅授課教師可呼叫。
    """
    payload = verify_token(credentials)
    teacher_id = payload.get("user_id")
    result = await run_in_db_pool(_sync_demote_student, course_id, teacher_id, target_user_id)
    logger.info(f"Teacher {teacher_id} demoted user {target_user_id} to student in course {course_id}")
    return result


def _sync_remove_member(course_id: int, requester_id: int, target_user_id: int):
    with engine.connect() as conn:
        # Verify requester is teacher or TA of the course
        check_teacher_or_course_ta(requester_id, course_id, conn)

        # Get course owner
        course_owner = conn.execute(
            text("SELECT teacher_id FROM courses WHERE id = :cid"),
            {"cid": course_id}
        ).fetchone()

        if not course_owner:
            raise HTTPException(status_code=404, detail="課程不存在")

        # Cannot remove the course teacher
        if target_user_id == course_owner.teacher_id:
            raise HTTPException(status_code=403, detail="無法移除課程授課教師")

        # Get target member info
        target_enrollment = conn.execute(
            text("SELECT role FROM enrollments WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        ).fetchone()

        if not target_enrollment:
            raise HTTPException(status_code=404, detail="該使用者非本課程成員")

        # If requester is a TA, they can only remove students
        is_owner = course_owner.teacher_id == requester_id
        if not is_owner:
            requester_enrollment = conn.execute(
                text("SELECT role FROM enrollments WHERE user_id = :uid AND course_id = :cid"),
                {"uid": requester_id, "cid": course_id}
            ).fetchone()
            
            if requester_enrollment and requester_enrollment.role == 'ta':
                if target_enrollment.role == 'ta':
                    raise HTTPException(status_code=403, detail="助教無權移除其他助教")

        # Execute removal
        conn.execute(
            text("DELETE FROM enrollments WHERE user_id = :uid AND course_id = :cid"),
            {"uid": target_user_id, "cid": course_id}
        )
        conn.commit()
        return {"message": "成員已成功從課堂移除"}


@router.delete(
    "/api/teacher/courses/{course_id}/members/{target_user_id}",
    tags=["Teachers"]
)
async def remove_course_member(
    course_id: int,
    target_user_id: int,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    將成員移除課堂。教師可移除任何人（除自己），助教僅能移除學生。
    """
    payload = verify_token(credentials)
    requester_id = payload.get("user_id")
    result = await run_in_db_pool(_sync_remove_member, course_id, requester_id, target_user_id)
    logger.info(f"User {requester_id} removed user {target_user_id} from course {course_id}")
    return result
