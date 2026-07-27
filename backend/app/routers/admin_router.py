"""
Admin router: 管理員後台操作 API

目前提供：
- 取得待審核教師列表
- 教師帳號審核通過
- 教師帳號審核拒絕

安全設計：
  使用現有 JWT 登入系統驗證，JWT payload 中 role == 'admin' 才可呼叫。
  管理員使用一般登入端點 (/api/auth/login) 取得 token，
  再帶入 Authorization: Bearer <token> 呼叫本 router 的端點。
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import Table, select, update
from backend.app.utils.time_utils import get_now_taipei
import json
from backend.app.utils.db_logger import engine, metadata
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import require_admin
from backend.app.services.email_service import (
    send_teacher_approval_email,
    send_teacher_rejection_email,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# 反射資料表
try:
    users_table = Table("users", metadata, autoload_with=engine)
    teacher_profiles_table = Table("teacher_profiles", metadata, autoload_with=engine)
    roles_table = Table("roles", metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting admin tables: {e}")


# ==================== Pydantic Schemas ====================

class TeacherReviewRequest(BaseModel):
    """教師審核請求"""
    user_id: int
    reason: Optional[str] = None  # 拒絕時可填寫說明


class TeacherReviewResponse(BaseModel):
    """教師審核回應"""
    user_id: int
    email: str
    full_name: str
    new_status: str
    email_sent: bool
    message: str


class UserSearchResponse(BaseModel):
    """使用者搜尋回應"""
    id: int
    email: str
    full_name: str
    role: str
    status: str
    created_at: Optional[str] = None


class SystemStatsResponse(BaseModel):
    """系統數據總覽回應"""
    teachers: int
    students: int
    courses: int
    ai_generations: int
    course_views: int
    pending_teachers: int


class UserStatsResponse(BaseModel):
    """使用者關聯資料統計回應"""
    user_id: int
    full_name: str
    email: str
    stats: list  # list of {table, count}


class ExperimentStatsResponse(BaseModel):
    teacher_stats: dict = {}
    student_stats: dict = {}
    daily_stats: list = []
    edit_ratio_distribution: list = []
    reading_engagement: list = []
    feedback_stats: dict = {}
    rq_metrics: dict = {}
    kp_source_types: dict = {}
    summarized_metrics: dict = {}

class SeedExtractRequest(BaseModel):
    job_id: int = Field(..., description="The original job ID to extract configuration from")




class FeedbackItem(BaseModel):
    """回饋中心項目"""
    id: int
    type: str  # 'report', 'rating', 'citation', 'question'
    user_name: str
    user_role: str
    course_name: Optional[str] = None
    course_id: Optional[int] = None
    content_name: Optional[str] = None
    content_id: Optional[int] = None
    question_id: Optional[int] = None
    title: str  # 摘要標題
    description: str  # 詳細描述
    rating: Optional[int] = None
    tags: Optional[List[str]] = None
    created_at: datetime


# ==================== API Endpoints ====================

@router.get("/system/stats", response_model=SystemStatsResponse, dependencies=[Depends(require_admin)])
async def get_system_stats():
    """取得系統數據總覽"""
    def _sync_system_stats():
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            def safe_count(query, params=None):
                try:
                    return conn.execute(sql_text(query), params or {}).scalar() or 0
                except Exception as e:
                    print(f"[stats] query failed: {e}")
                    conn.rollback()
                    return 0

            teacher_role_id = conn.execute(sql_text(
                "SELECT id FROM roles WHERE name = 'teacher' LIMIT 1"
            )).scalar()
            student_role_id = conn.execute(sql_text(
                "SELECT id FROM roles WHERE name = 'student' LIMIT 1"
            )).scalar()

            teachers = safe_count(
                "SELECT COUNT(*) FROM users WHERE role_id = :rid",
                {"rid": teacher_role_id}
            ) if teacher_role_id else 0

            students = safe_count(
                "SELECT COUNT(*) FROM users WHERE role_id = :rid",
                {"rid": student_role_id}
            ) if student_role_id else 0

            courses = safe_count("SELECT COUNT(*) FROM courses WHERE is_deleted IS NOT TRUE")

            ai_generations = safe_count("SELECT COUNT(*) FROM generated_contents")
            if ai_generations == 0:
                ai_generations = safe_count("SELECT COUNT(*) FROM orchestration_jobs")

            course_views = safe_count("SELECT COUNT(*) FROM attachment_reading_logs")

            pending_teachers = safe_count(
                "SELECT COUNT(*) FROM users WHERE status = 'pending' AND role_id = :rid",
                {"rid": teacher_role_id}
            ) if teacher_role_id else 0

            return {
                "teachers": teachers,
                "students": students,
                "courses": courses,
                "ai_generations": ai_generations,
                "course_views": course_views,
                "pending_teachers": pending_teachers
            }

    return await run_in_db_pool(_sync_system_stats)


@router.get("/teachers/pending", dependencies=[Depends(require_admin)])
async def list_pending_teachers():
    """
    取得所有待審核教師列表

    需要以管理員帳號登入取得 JWT，帶入 Authorization: Bearer <token>
    """
    def _sync_list_pending():
        with engine.connect() as conn:
            teacher_role_q = select(roles_table.c.id).where(roles_table.c.name == "teacher")
            teacher_role_row = conn.execute(teacher_role_q).fetchone()
            if not teacher_role_row:
                return []
            teacher_role_id = teacher_role_row[0]

            query = (
                select(
                    users_table.c.id,
                    users_table.c.email,
                    users_table.c.full_name,
                    users_table.c.created_time,
                    teacher_profiles_table.c.institution,
                    teacher_profiles_table.c.proof_document_url,
                )
                .join(
                    teacher_profiles_table,
                    teacher_profiles_table.c.user_id == users_table.c.id,
                )
                .where(
                    (users_table.c.status == "pending") &
                    (users_table.c.role_id == teacher_role_id)
                )
                .order_by(users_table.c.created_time.asc())
            )
            rows = conn.execute(query).fetchall()
            return [
                {
                    "user_id": row[0],
                    "email": row[1],
                    "full_name": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                    "institution": row[4] or "",
                    "proof_document_url": row[5],
                }
                for row in rows
            ]

    teachers = await run_in_db_pool(_sync_list_pending)
    return {"pending_teachers": teachers, "count": len(teachers)}


@router.post("/teachers/approve", response_model=TeacherReviewResponse, dependencies=[Depends(require_admin)])
async def approve_teacher(request: TeacherReviewRequest):
    """
    審核通過教師帳號

    流程：
    1. 驗證 user_id 存在且目前為 pending 狀態
    2. 將 users.status 更新為 active
    3. 發送審核通過通知信給教師

    需要以管理員帳號登入取得 JWT，帶入 Authorization: Bearer <token>
    """
    def _sync_approve(user_id):
        with engine.connect() as conn:
            user_row = conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.email,
                    users_table.c.full_name,
                    users_table.c.status,
                ).where(users_table.c.id == user_id)
            ).fetchone()

            if not user_row:
                return None, "找不到此使用者"

            uid, email, full_name, status = user_row

            if status == "active":
                return None, "此帳號已是啟用狀態"
            if status == "rejected":
                return None, "此帳號已被拒絕，若要重新審核請先將狀態改回 pending"

            conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(status="active")
            )
            conn.commit()
            return {"email": email, "full_name": full_name}, None

    result, error = await run_in_db_pool(_sync_approve, request.user_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 發送通知信，失敗不影響審核結果
    email_sent = False
    try:
        email_sent = await run_in_db_pool(
            send_teacher_approval_email,
            result["email"],
            result["full_name"],
        )
    except Exception as exc:
        print(f"發送審核通過通知信失敗: {exc}")

    return TeacherReviewResponse(
        user_id=request.user_id,
        email=result["email"],
        full_name=result["full_name"],
        new_status="active",
        email_sent=email_sent,
        message="審核通過，帳號已啟用。" + ("" if email_sent else "（通知信發送失敗，請手動通知教師）"),
    )


@router.post("/teachers/reject", response_model=TeacherReviewResponse, dependencies=[Depends(require_admin)])
async def reject_teacher(request: TeacherReviewRequest):
    """
    拒絕教師帳號申請

    流程：
    1. 驗證 user_id 存在且目前為 pending 狀態
    2. 將 users.status 更新為 rejected
    3. 發送審核拒絕通知信給教師（可附帶說明原因）

    需要以管理員帳號登入取得 JWT，帶入 Authorization: Bearer <token>
    """
    def _sync_reject(user_id):
        with engine.connect() as conn:
            user_row = conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.email,
                    users_table.c.full_name,
                    users_table.c.status,
                ).where(users_table.c.id == user_id)
            ).fetchone()

            if not user_row:
                return None, "找不到此使用者"

            uid, email, full_name, status = user_row

            if status == "rejected":
                return None, "此帳號已是拒絕狀態"
            if status == "active":
                return None, "此帳號已是啟用狀態，若要拒絕請先將狀態改回 pending"

            conn.execute(
                update(users_table)
                .where(users_table.c.id == user_id)
                .values(status="rejected")
            )
            conn.commit()
            return {"email": email, "full_name": full_name}, None

    result, error = await run_in_db_pool(_sync_reject, request.user_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 發送拒絕通知信
    email_sent = False
    try:
        email_sent = await run_in_db_pool(
            send_teacher_rejection_email,
            result["email"],
            result["full_name"],
            request.reason or "",
        )
    except Exception as exc:
        print(f"發送審核拒絕通知信失敗: {exc}")

    return TeacherReviewResponse(
        user_id=request.user_id,
        email=result["email"],
        full_name=result["full_name"],
        new_status="rejected",
        email_sent=email_sent,
        message="審核拒絕，帳號已停用。" + ("" if email_sent else "（通知信發送失敗，請手動通知教師）"),
    )


# ==================== User Management Endpoints ====================

@router.get("/users/search", response_model=list[UserSearchResponse], dependencies=[Depends(require_admin)])
async def search_users(keyword: str):
    """搜尋使用者 (by name or email)"""
    def _sync_search(kw):
        with engine.connect() as conn:
            from sqlalchemy import or_
            query = (
                select(
                    users_table.c.id,
                    users_table.c.email,
                    users_table.c.full_name,
                    roles_table.c.name.label("role"),
                    users_table.c.status,
                    users_table.c.created_time
                )
                .join(roles_table, roles_table.c.id == users_table.c.role_id)
                .where(
                    or_(
                        users_table.c.email.ilike(f"%{kw}%"),
                        users_table.c.full_name.ilike(f"%{kw}%")
                    )
                )
                .limit(20)
            )
            rows = conn.execute(query).fetchall()
            return [
                {
                    "id": row[0],
                    "email": row[1],
                    "full_name": row[2],
                    "role": row[3],
                    "status": row[4],
                    "created_at": row[5].isoformat() if row[5] else None
                }
                for row in rows
            ]

    return await run_in_db_pool(_sync_search, keyword)


@router.get("/users/{user_id}/stats", response_model=UserStatsResponse, dependencies=[Depends(require_admin)])
async def get_user_stats(user_id: int):
    """取得使用者關聯資料統計"""
    from sqlalchemy import text
    def _sync_stats(uid):
        fk_query = """
        SELECT tc.table_name, kcu.column_name 
        FROM information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu 
          ON tc.constraint_name = kcu.constraint_name 
          AND tc.table_schema = kcu.table_schema 
        JOIN information_schema.constraint_column_usage AS ccu 
          ON ccu.constraint_name = tc.constraint_name 
          AND ccu.table_schema = tc.table_schema 
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='users' AND ccu.column_name='id';
        """
        with engine.connect() as conn:
            user_info = conn.execute(select(users_table.c.email, users_table.c.full_name).where(users_table.c.id == uid)).fetchone()
            if not user_info:
                return None
            
            summary = []
            fk_tables = conn.execute(text(fk_query)).fetchall()
            for table_name, column_name in fk_tables:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :uid"), {"uid": uid}).scalar()
                if count > 0:
                    summary.append({"table": table_name, "count": count})
            
            return {
                "user_id": uid,
                "full_name": user_info.full_name,
                "email": user_info.email,
                "stats": summary
            }

    res = await run_in_db_pool(_sync_stats, user_id)
    if not res:
        raise HTTPException(status_code=404, detail="User not found")
    return res


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int):
    """刪除使用者與其所有關聯資料 (不可逆)"""
    from sqlalchemy import text
    def _sync_delete(uid):
        # 這裡復用之前的腳本邏輯，但為了安全起見再次獲取 FK
        fk_query = """
        SELECT tc.table_name, kcu.column_name 
        FROM information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu 
          ON tc.constraint_name = kcu.constraint_name 
          AND tc.table_schema = kcu.table_schema 
        JOIN information_schema.constraint_column_usage AS ccu 
          ON ccu.constraint_name = tc.constraint_name 
          AND ccu.table_schema = tc.table_schema 
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='users' AND ccu.column_name='id';
        """
        with engine.begin() as conn:
            # 取得間接關連清單
            jobs_q = text("SELECT id FROM orchestration_jobs WHERE user_id = :uid")
            job_ids = [row[0] for row in conn.execute(jobs_q, {"uid": uid}).fetchall()]
            
            courses_q = text("SELECT id FROM courses WHERE teacher_id = :uid")
            course_ids = [row[0] for row in conn.execute(courses_q, {"uid": uid}).fetchall()]
            
            # 1. 直接關聯
            fk_tables = conn.execute(text(fk_query)).fetchall()
            for t, c in fk_tables:
                conn.execute(text(f"DELETE FROM {t} WHERE {c} = :uid"), {"uid": uid})
            
            # 2. 間接關聯 jobs
            if job_ids:
                conn.execute(text("DELETE FROM agent_tasks WHERE job_id = ANY(:jids)"), {"jids": job_ids})
                conn.execute(text("DELETE FROM agent_task_sources WHERE job_id = ANY(:jids)"), {"jids": job_ids})
                conn.execute(text("DELETE FROM orchestration_jobs WHERE id = ANY(:jids)"), {"jids": job_ids})
            
            # 3. 間接關聯 courses
            if course_ids:
                conn.execute(text("DELETE FROM course_contents WHERE course_id = ANY(:cids)"), {"cids": course_ids})
                conn.execute(text("DELETE FROM course_units WHERE course_id = ANY(:cids)"), {"cids": course_ids})
                conn.execute(text("DELETE FROM student_course_enrollment WHERE course_id = ANY(:cids)"), {"cids": course_ids})
                conn.execute(text("DELETE FROM material_ratings WHERE course_id = ANY(:cids)"), {"cids": course_ids})
                conn.execute(text("DELETE FROM announcements WHERE course_id = ANY(:cids)"), {"cids": course_ids})
                conn.execute(text("DELETE FROM courses WHERE id = ANY(:cids)"), {"cids": course_ids})

            # 4. 刪除 User
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
            return True

    success = await run_in_db_pool(_sync_delete, user_id)
    if success:
        return {"message": "User and all related data deleted successfully"}
    return {"message": "Failed to delete user"}


# ==================== Course Management Endpoints ====================

@router.get("/courses", dependencies=[Depends(require_admin)])
async def get_all_courses():
    """取得所有課程列表 (課程管理)"""
    from sqlalchemy import text
    def _sync_courses():
        with engine.connect() as conn:
            q = text("""
                SELECT c.id, c.name, c.semester_name AS semester,
                       u.full_name as teacher_name, u.email as teacher_email,
                       c.created_at
                FROM courses c
                LEFT JOIN users u ON c.teacher_id = u.id
                WHERE c.is_deleted IS NOT TRUE
                ORDER BY c.created_at DESC
            """)
            rows = conn.execute(q).fetchall()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "semester": r.semester or "",
                    "teacher_name": r.teacher_name or "未知",
                    "teacher_email": r.teacher_email,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    return await run_in_db_pool(_sync_courses)


@router.get("/feedback/all", response_model=List[FeedbackItem], dependencies=[Depends(require_admin)])
async def get_all_feedback():
    """取得所有使用者回饋 (意見回報、學生評教材、教師評生成品質)"""
    def _sync_get_feedback():
        with engine.connect() as conn:
            from sqlalchemy import text as sql_text
            results = []

            # 1. 意見回饋中心回報 (feedback_reports)
            try:
                # Try fetching with status column; fall back gracefully if column missing
                try:
                    q1 = sql_text("""
                        SELECT f.id, u.full_name as user_name, f.user_role,
                               f.description, f.selected_problems as tags,
                               f.created_at,
                               COALESCE(f.status, 'pending') as status
                        FROM feedback_reports f
                        LEFT JOIN users u ON f.user_id = u.id
                        ORDER BY f.created_at DESC
                    """)
                    rows_q1 = conn.execute(q1).fetchall()
                except Exception:
                    conn.rollback()
                    q1 = sql_text("""
                        SELECT f.id, u.full_name as user_name, f.user_role,
                               f.description, f.selected_problems as tags,
                               f.created_at
                        FROM feedback_reports f
                        LEFT JOIN users u ON f.user_id = u.id
                        ORDER BY f.created_at DESC
                    """)
                    rows_q1 = conn.execute(q1).fetchall()

                for r in rows_q1:
                    raw_tags = r.tags
                    if isinstance(raw_tags, list):
                        tags = raw_tags
                    elif raw_tags:
                        try:
                            tags = json.loads(raw_tags)
                        except Exception:
                            tags = [raw_tags]
                    else:
                        tags = []
                    results.append({
                        "id": r.id,
                        "type": "report",
                        "user_name": r.user_name or "未知用戶",
                        "user_role": r.user_role or "student",
                        "title": "問題回報",
                        "description": r.description or "",
                        "tags": tags,
                        "status": getattr(r, "status", "pending"),
                        "created_at": r.created_at,
                    })
            except Exception as e:
                print(f"[feedback] feedback_reports query failed: {e}")
                conn.rollback()

            # 2. 學生評教材品質 (material_ratings)
            try:
                q2 = sql_text("""
                    SELECT m.id, u.full_name as user_name,
                           c.name as course_name, c.id as course_id,
                           cc.title as content_name, cc.id as content_id,
                           m.rating, m.created_at
                    FROM material_ratings m
                    LEFT JOIN users u ON m.user_id = u.id
                    LEFT JOIN courses c ON m.course_id = c.id
                    LEFT JOIN course_contents cc ON m.content_id = cc.id
                    ORDER BY m.created_at DESC
                """)
                for r in conn.execute(q2).fetchall():
                    rating_data = r.rating if isinstance(r.rating, dict) else (json.loads(r.rating) if r.rating else {})
                    score = rating_data.get("score") or rating_data.get("overall")
                    feedback_text = rating_data.get("feedback") or "無文字回饋"
                    content_label = r.content_name or "未知教材"
                    results.append({
                        "id": r.id,
                        "type": "material_rating",
                        "user_name": r.user_name or "未知學員",
                        "user_role": "student",
                        "course_name": r.course_name,
                        "course_id": r.course_id,
                        "content_name": content_label,
                        "content_id": r.content_id,
                        "title": f"教材評分：{content_label}",
                        "description": feedback_text,
                        "rating": score,
                        "created_at": r.created_at,
                    })
            except Exception as e:
                print(f"[feedback] material_ratings query failed: {e}")
                conn.rollback()

            # 3. 教師評 AI 生成品質 (generated_contents.teacher_rating)
            try:
                q3 = sql_text("""
                    SELECT gc.id, u.full_name as user_name,
                           gc.title as content_title,
                           gc.teacher_rating, gc.updated_at as rated_at
                    FROM generated_contents gc
                    LEFT JOIN orchestration_jobs oj ON oj.final_output_id = gc.id
                    LEFT JOIN users u ON oj.user_id = u.id
                    WHERE gc.teacher_rating IS NOT NULL
                    ORDER BY gc.updated_at DESC
                """)
                for r in conn.execute(q3).fetchall():
                    rating_data = r.teacher_rating if isinstance(r.teacher_rating, dict) else (json.loads(r.teacher_rating) if r.teacher_rating else {})
                    score = rating_data.get("score")
                    feedback_text = rating_data.get("feedback") or "無文字回饋"
                    content_label = (r.content_title or "未知內容")[:40]
                    results.append({
                        "id": r.id,
                        "type": "teacher_rating",
                        "user_name": r.user_name or "未知教師",
                        "user_role": "teacher",
                        "title": f"生成品質評分：{content_label}",
                        "description": feedback_text,
                        "rating": score,
                        "created_at": r.rated_at,
                    })
            except Exception as e:
                print(f"[feedback] generated_contents teacher_rating query failed: {e}")
                conn.rollback()

            # 4. Reference Drawer 回饋 (reference_feedbacks)
            try:
                q4 = sql_text("""
                    SELECT rf.id, u.full_name as user_name,
                           rc.chunk_text as chunk_text,
                           rf.rating, rf.comment, rf.error_types as tags,
                           rf.created_at, rf.question_id
                    FROM reference_feedbacks rf
                    LEFT JOIN document_chunks rc ON rf.chunk_id = rc.id
                    LEFT JOIN users u ON rf.teacher_id = u.id
                    ORDER BY rf.created_at DESC
                    LIMIT 200
                """)
                for r in conn.execute(q4).fetchall():
                    chunk_preview = (r.chunk_text or "")[:60].replace("\n", " ")
                    raw_tags = r.tags
                    if isinstance(raw_tags, list):
                        ref_tags = raw_tags
                    elif raw_tags:
                        try:
                            ref_tags = json.loads(raw_tags)
                        except Exception:
                            ref_tags = [raw_tags]
                    else:
                        ref_tags = []
                    
                    # Construct description with QID for the admin
                    feedback_desc = r.comment or chunk_preview or "無評論"
                    id_label = f"[QID: {r.question_id or '?'}]"
                    
                    results.append({
                        "id": r.id,
                        "type": "reference",
                        "user_name": r.user_name or "教師",
                        "user_role": "teacher",
                        "title": f"引用回饋 {id_label}",
                        "description": feedback_desc,
                        "rating": r.rating,
                        "question_id": r.question_id,
                        "tags": ref_tags,
                        "created_at": r.created_at,
                    })
            except Exception as e:
                print(f"[feedback] reference_feedbacks query failed: {e}")
                conn.rollback()

            def _sort_key(x):
                v = x.get("created_at")
                if v is None:
                    return ""
                if hasattr(v, 'isoformat'):
                    return v.isoformat()
                return str(v)

            results.sort(key=_sort_key, reverse=True)
            return results

    return await run_in_db_pool(_sync_get_feedback)


@router.patch("/feedback/reports/{report_id}/status", dependencies=[Depends(require_admin)])
async def mark_feedback_report_status(report_id: int, status: str = "done"):
    """將問題回報標記為已處理 (status: pending | done)"""
    if status not in ("pending", "done"):
        raise HTTPException(status_code=400, detail="status must be 'pending' or 'done'")

    def _sync_update(rid: int, new_status: str):
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            # Ensure status column exists; add it if not
            try:
                conn.execute(sql_text("""
                    ALTER TABLE feedback_reports
                    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'
                """))
                conn.commit()
            except Exception as e:
                print(f"[feedback] ensure status column: {e}")
                conn.rollback()

            try:
                res = conn.execute(sql_text("""
                    UPDATE feedback_reports
                    SET status = :status
                    WHERE id = :id
                    RETURNING id
                """), {"status": new_status, "id": rid})
                conn.commit()
                return res.fetchone() is not None
            except Exception as e:
                print(f"[feedback] mark status failed: {e}")
                conn.rollback()
                return False

    updated = await run_in_db_pool(_sync_update, report_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"id": report_id, "status": status}


@router.get("/experiment/stats", response_model=ExperimentStatsResponse, dependencies=[Depends(require_admin)])
async def get_experiment_stats(course_id: Optional[int] = None, unit_id: Optional[int] = None, days: int = 30):
    """取得實驗數據統計分析，支援課程與單元篩選"""
    def _sync_experiment_stats(c_id: Optional[int], u_id: Optional[int], d: int):
        from sqlalchemy import text as sql_text
        from datetime import datetime, timedelta
        import pandas as pd
        import numpy as np
        import json
        
        # 僅分析 2024-03-05 以後的數據
        EXP_START_DATE = "2024-03-05"
        since_date_dt = get_now_taipei() - timedelta(days=d)
        effective_start_date = max(since_date_dt, datetime.strptime(EXP_START_DATE, "%Y-%m-%d").replace(tzinfo=since_date_dt.tzinfo))
        since_date = effective_start_date.strftime('%Y-%m-%d')
        
        with engine.connect() as conn:
            # --- 角色過濾條件 ---
            c_id_val = c_id if c_id else 0
            valid_students_q = f"""
                SELECT u.id FROM users u
                WHERE u.role_id != 1
                AND NOT EXISTS (
                    SELECT 1 FROM enrollments e 
                    WHERE e.user_id = u.id 
                    AND e.role = 'ta'
                    {f"AND e.course_id = {c_id_val}" if c_id_val > 0 else ""}
                )
            """
            try:
                valid_student_ids = [r[0] for r in conn.execute(sql_text(valid_students_q)).fetchall()]
            except Exception as e:
                print(f"[experiment] fetch valid students failed: {e}")
                valid_student_ids = []

            if valid_student_ids:
                ids_str = ','.join(map(str, valid_student_ids))
                student_role_filter = f"AND u.id IN ({ids_str})"
            else:
                student_role_filter = "AND 1=0"
            
            # 1. Teacher Prep (generator_setting_logs)
            prep_query = f"""
                SELECT src.*, oj.input_config->'job_context'->>'course_id' as job_course_id,
                       oj.input_config->'job_context'->>'unit_id' as job_unit_id
                FROM generator_setting_logs src
                LEFT JOIN orchestration_jobs oj ON src.job_id = oj.id
                WHERE src.created_at >= '{since_date}'
            """
            if c_id: prep_query += f" AND (oj.input_config->'job_context'->>'course_id')::int = {c_id}"
            if u_id: prep_query += f" AND (oj.input_config->'job_context'->>'unit_id')::int = {u_id}"
            df_prep = pd.read_sql(sql_text(prep_query), conn)
            
            # 0. Fetch Knowledge Points Source Types Mapping
            kp_source_types = {}
            try:
                kp_map_query = "SELECT name, source_type FROM knowledge_points"
                where_clauses = []
                if c_id: where_clauses.append(f"course_id = {c_id}")
                if u_id: where_clauses.append(f"unit_id = {u_id}")
                if where_clauses:
                    kp_map_query += " WHERE " + " AND ".join(where_clauses)
                
                kp_rows = conn.execute(sql_text(kp_map_query)).fetchall()
                kp_source_types = {row[0]: row[1] for row in kp_rows}
            except Exception as e:
                print(f"[experiment] kp map query failed: {e}")
                conn.rollback()

            
            if c_id:
                # Pre-fetch matching job_ids using the expression index for extreme speed
                job_ids_q = f"SELECT id FROM orchestration_jobs WHERE (input_config->'job_context'->>'course_id')::int = {c_id}"
                c_job_ids = [r[0] for r in conn.execute(sql_text(job_ids_q)).fetchall()]
            else:
                c_job_ids = []

            # 2. Generated Contents (Joined with course_contents for edit_history aggregation)
            if c_id and not c_job_ids:
                df_content = pd.DataFrame()
            else:
                content_query = f"""
                    SELECT src.*, cc.edit_history as course_edit_history, cc.id as course_content_id,
                           cc.title as course_title,
                           oj.id as job_id,
                           oj.input_config as job_input_config,
                           oj.used_models,
                           oj.total_cost_usd,
                           oj.total_cost_twd,
                           oj.environmental_impact,
                           oj.total_prompt_tokens,
                           oj.total_completion_tokens,
                           jsonb_array_length(src.source_preview_logs) as source_preview_count
                    FROM generated_contents src
                    INNER JOIN agent_tasks at ON src.source_agent_task_id = at.id
                    INNER JOIN orchestration_jobs oj ON at.job_id = oj.id
                    LEFT JOIN course_contents cc ON (src.id = cc.source_id AND cc.source_type = 'generated_content')
                    WHERE src.created_at >= '{since_date}'
                """
                if c_job_ids:
                    ids_str = ','.join(map(str, c_job_ids))
                    content_query += f" AND oj.id IN ({ids_str})"
                
                if u_id: content_query += f" AND (oj.input_config->'job_context'->>'unit_id')::int = {u_id}"
                
                df_content = pd.read_sql(sql_text(content_query), conn)

            # Map session_id from df_prep to df_content
            if not df_content.empty and not df_prep.empty:
                prep_sessions = df_prep.dropna(subset=['job_id', 'session_id']).set_index('job_id')['session_id'].to_dict()
                df_content['session_id'] = df_content['job_id'].map(prep_sessions)
            elif not df_content.empty:
                df_content['session_id'] = None

            # 5. Agent Tasks (for RAG metrics & Critic scores)
            job_ids = []
            if not df_content.empty: job_ids.extend(df_content['job_id'].dropna().unique().tolist())
            if not df_prep.empty: job_ids.extend(df_prep['job_id'].dropna().unique().tolist())
            job_ids = [int(jid) for jid in set(job_ids)]
            
            if job_ids:
                tasks_query = f"SELECT * FROM agent_tasks WHERE job_id IN ({','.join(map(str, job_ids))})"
                df_tasks = pd.read_sql(sql_text(tasks_query), conn)
                
                # Fetch structured evaluations from task_evaluations
                evals_query = f"SELECT * FROM task_evaluations WHERE job_id IN ({','.join(map(str, job_ids))})"
                df_evals = pd.read_sql(sql_text(evals_query), conn)
            else:
                df_tasks = pd.DataFrame()
                df_evals = pd.DataFrame()

            # 6. Reference Feedbacks
            feedback_query = f"SELECT * FROM reference_feedbacks WHERE created_at >= '{since_date}'"
            df_feedback = pd.read_sql(sql_text(feedback_query), conn)
            
            # 3. Student Reading (material_reading_logs)
            reading_query = f"""
                SELECT src.*, u.full_name FROM material_reading_logs src
                JOIN users u ON src.user_id = u.id
                WHERE src.created_at >= '{since_date}'
                {student_role_filter}
            """
            if c_id: reading_query += f" AND EXISTS (SELECT 1 FROM course_units cu WHERE cu.id = src.unit_id AND cu.course_id = {c_id})"
            if u_id: reading_query += f" AND src.unit_id = {u_id}"
            df_reading = pd.read_sql(sql_text(reading_query), conn)
            
            # 4. Student Questions (student_question_logs)
            q_query = f"""
                SELECT src.*, u.full_name FROM student_question_logs src
                JOIN users u ON src.student_id = u.id
                WHERE src.answered_at >= '{since_date}'
                {student_role_filter}
            """
            if c_id: q_query += f" AND src.course_id = {c_id}"
            if u_id: q_query += f" AND src.unit_id = {u_id}"
            df_questions = pd.read_sql(sql_text(q_query), conn)

            # 7. Student Chatbot Turn Logs (for SRL Inquiry analysis)
            turn_query = f"""
                SELECT src.*, u.full_name FROM student_chatbot_turn_logs src
                JOIN users u ON src.student_id = u.id
                WHERE src.created_at >= '{since_date}'
                {student_role_filter}
            """
            if c_id: turn_query += f" AND src.course_id = {c_id}"
            if u_id: turn_query += f" AND src.unit_id = {u_id}"
            df_turns = pd.read_sql(sql_text(turn_query), conn)

            # 8. Student Chatbot Dialogs (for direct KP mapping)
            dialog_query = f"""
                SELECT src.* FROM student_chatbot_dialogs src
                WHERE src.created_at >= '{since_date}'
                AND src.knowledge_point_id IS NOT NULL
            """
            if valid_student_ids:
                ids_str = ','.join(map(str, valid_student_ids))
                dialog_query += f" AND src.student_id IN ({ids_str})"
            else:
                dialog_query += " AND 1=0"
                
            if c_id: dialog_query += f" AND src.course_id = {c_id}"
            if u_id: dialog_query += f" AND src.unit_id = {u_id}"
            df_dialogs_kp = pd.read_sql(sql_text(dialog_query), conn)
            
            # --- SRL & LEI Metrics Calculation ---
            
            # core KPs for deeper inquiry analysis
            core_kp_names = set(kp_source_types.keys())
            lower_core_kp_names = {kp.lower(): kp for kp in core_kp_names}
            # Teacher specified KPs (source_type = 'manual')
            teacher_specified_kp_names = {name for name, st in kp_source_types.items() if st == 'manual'}
            # Map ID to name for df_dialogs_kp
            kp_id_to_name = {}
            try:
                kp_id_map_query = "SELECT id, name FROM knowledge_points"
                if c_id: kp_id_map_query += f" WHERE course_id = {c_id}"
                kp_id_rows = conn.execute(sql_text(kp_id_map_query)).fetchall()
                kp_id_to_name = {row[0]: row[1] for row in kp_id_rows}
            except Exception as e:
                print(f"[experiment] kp id map query failed: {e}")
                conn.rollback()
            
            # Group by student and unit_session_id for behavior analysis
            student_sessions = {}
            
            # Combine all student IDs involved
            all_student_ids = set()
            if not df_reading.empty: all_student_ids.update(df_reading['user_id'].dropna().unique())
            if not df_questions.empty: all_student_ids.update(df_questions['student_id'].dropna().unique())
            if not df_turns.empty: all_student_ids.update(df_turns['student_id'].dropna().unique())
            
            lei_records = []
            student_names = {}
            if not df_reading.empty:
                student_names.update(dict(zip(df_reading['user_id'], df_reading['full_name'])))
            if not df_questions.empty:
                student_names.update(dict(zip(df_questions['student_id'], df_questions['full_name'])))
            if not df_turns.empty:
                student_names.update(dict(zip(df_turns['student_id'], df_turns['full_name'])))
            
            for s_id in all_student_ids:
                s_id = int(s_id)
                s_reading = df_reading[df_reading['user_id'] == s_id].copy() if not df_reading.empty else pd.DataFrame()
                s_questions = df_questions[df_questions['student_id'] == s_id].copy() if not df_questions.empty else pd.DataFrame()
                s_turns = df_turns[df_turns['student_id'] == s_id].copy() if not df_turns.empty else pd.DataFrame()
                
                # 1. Reading Dimension (T * D)
                # Weighted average if multiple sessions
                if not s_reading.empty:
                    T = s_reading['stay_duration_seconds'].sum()
                    D = s_reading['max_scroll_depth'].mean()
                    C = s_reading['citation_interactions'].apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
                else:
                    T, D, C = 0, 0, 0
                
                # 2. Testing Dimension (AT)
                # Correctness scoring: Correct=100, Partial=90, Incorrect=25, Unanswered=0
                if not s_questions.empty:
                    def _score_correctness(c):
                        if c == 'correct': return 100
                        if c == 'partial': return 90
                        if c == 'incorrect': return 25
                        return 0
                    s_questions['score'] = s_questions['correctness'].apply(_score_correctness)
                    A_score = s_questions['score'].mean()
                    question_count = len(s_questions)
                else:
                    A_score, question_count = 0, 0
                
                # 3. Inquiry Dimension (M_final)
                # M_final = 0.4 * Norm(M_count) + 0.6 * Norm(M_kp_depth)
                M_count = len(s_turns)
                triggered_kps = set()
                
                # A. Check dialogs table for direct KP association (Phase 3+)
                s_dialogs = df_dialogs_kp[df_dialogs_kp['student_id'] == s_id]
                if not s_dialogs.empty:
                    for _, diag in s_dialogs.iterrows():
                        kp_id = diag.get('knowledge_point_id')
                        if kp_id in kp_id_to_name:
                            triggered_kps.add(kp_id_to_name[kp_id])

                # B. Analyze RAG top results for fallback/supplementary KP mapping
                if not s_turns.empty:
                    for _, turn in s_turns.iterrows():
                        rag_results = turn.get('rag_top_results')
                        if isinstance(rag_results, str):
                            try: rag_results = json.loads(rag_results)
                            except: rag_results = None
                                
                        if isinstance(rag_results, list):
                            for result in rag_results:
                                text_content = (result.get('text') or '').lower()
                                metadata_str = str(result.get('metadata') or {}).lower()
                                combined_text = text_content + " " + metadata_str
                                for lower_kp, orig_kp in lower_core_kp_names.items():
                                    if lower_kp in combined_text:
                                        triggered_kps.add(orig_kp)
                
                # C. Final Intersection: Only count teacher-specified KPs
                intersected_kps = triggered_kps.intersection(teacher_specified_kp_names)
                M_kp_depth = len(intersected_kps)
                
                # 4. Remedial Dimension (R)
                # Sequence: Error -> Reading -> Retry (success or same question)
                # Simplified: count sessions where a student had an error then did reading in same unit
                remedial_count = 0
                if not s_questions.empty and not s_reading.empty:
                    # Sort both by time
                    q_errors = s_questions[s_questions['correctness'] != 'correct'].sort_values('answered_at')
                    readings = s_reading.sort_values('created_at')
                    q_success = s_questions[s_questions['correctness'] == 'correct'].sort_values('answered_at')
                    
                    for _, err in q_errors.iterrows():
                        # Find if there was a reading after this error but before a success or next retry
                        unit_readings = readings[(readings['created_at'] > err['answered_at']) & (readings['unit_id'] == err['unit_id'])]
                        if not unit_readings.empty:
                            remedial_count += 1
                
                # Save raw metrics for normalization later
                lei_records.append({
                    "student_id": s_id,
                    "student_name": student_names.get(s_id, f"學生 {s_id}"),
                    "metrics": {
                        "T": float(T),
                        "D": float(D),
                        "C": int(C),
                        "A": float(A_score),
                        "M_count": int(M_count),
                        "M_kp_depth": int(M_kp_depth),
                        "R": int(remedial_count),
                        "question_count": int(question_count)
                    },
                    "triggered_kps": list(intersected_kps)
                })

            # Normalization and Weighted LEI calculation
            df_lei = pd.DataFrame()
            if lei_records:
                df_lei = pd.DataFrame([ {**r['metrics'], 'student_id': r['student_id']} for r in lei_records ])
                
                # Helper for normalization (0-1)
                def _norm(col):
                    if df_lei[col].max() == df_lei[col].min(): return df_lei[col].apply(lambda x: 1.0 if x > 0 else 0.0)
                    return (df_lei[col] - df_lei[col].min()) / (df_lei[col].max() - df_lei[col].min())
                
                # Calculate Dimension Scores
                df_lei['s_reading'] = (_norm('T') * _norm('D')).clip(0, 1)
                df_lei['s_tracing'] = _norm('C')
                
                # Inquiry score calculation
                norm_m_count = _norm('M_count')
                norm_m_depth = _norm('M_kp_depth')
                df_lei['s_inquiry'] = (0.4 * norm_m_count + 0.6 * norm_m_depth)
                
                # Testing score (normalized by correctness rate and participation)
                df_lei['s_testing'] = (_norm('A') * 0.7 + _norm('question_count') * 0.3)
                
                # Remedial score
                df_lei['s_remedial'] = _norm('R')
                
                # Final LEI Score (Weighted sum as per plan)
                # Weights: Reading: 25%, Tracing: 10%, Inquiry: 20%, Testing: 20%, Remedial: 25%
                df_lei['lei_score'] = (
                    df_lei['s_reading'] * 0.25 +
                    df_lei['s_tracing'] * 0.10 +
                    df_lei['s_inquiry'] * 0.20 +
                    df_lei['s_testing'] * 0.20 +
                    df_lei['s_remedial'] * 0.25
                ) * 100
                
                # Calculate Quartiles for LEI
                quartiles = {
                    "p25": float(df_lei['lei_score'].quantile(0.25)),
                    "p50": float(df_lei['lei_score'].quantile(0.50)),
                    "p75": float(df_lei['lei_score'].quantile(0.75))
                }
                
                # Enrichment for final output
                for i, record in enumerate(lei_records):
                    row = df_lei.iloc[i]
                    record['lei_score'] = float(row['lei_score'])
                    record['dimensions'] = {
                        "reading": float(row['s_reading']),
                        "tracing": float(row['s_tracing']),
                        "inquiry": float(row['s_inquiry']),
                        "testing": float(row['s_testing']),
                        "remedial": float(row['s_remedial'])
                    }
            else:
                quartiles = {"p25": 0, "p50": 0, "p75": 0}

            # KP Alignment Analysis: Teacher Anchors vs Student Inquiry
            kp_alignment = []
            for kp_name in core_kp_names:
                adoption_count = sum(1 for r in lei_records if kp_name in r['triggered_kps'])
                kp_alignment.append({
                    "kp_name": kp_name,
                    "student_inquiry_count": adoption_count,
                    "source_type": kp_source_types.get(kp_name, 'unknown')
                })

            # --- RQ1-RQ4 指標計算 ---
            rq_metrics = {
                "rq1": {"quality_score": 0, "kp_adoption": 0, "edit_efficiency": [], "action_distribution": {}},
                "rq2": {"cognitive_load_trend": [], "trust_check": []},
                "rq3": {"remedial_rate": 0, "reading_load_correlation": []},
                "rq4": {"citation_trust": 0, "nav_usage": {}},
                "srl_analysis": {
                    "lei_distribution": lei_records,
                    "lei_quartiles": quartiles,
                    "overall_lei": float(df_lei['lei_score'].mean()) if not df_lei.empty else 0.0,
                    "dimension_averages": {
                        "s_reading": float(df_lei['s_reading'].mean()) if not df_lei.empty else 0.0,
                        "s_tracing": float(df_lei['s_tracing'].mean()) if not df_lei.empty else 0.0,
                        "s_inquiry": float(df_lei['s_inquiry'].mean()) if not df_lei.empty else 0.0,
                        "s_testing": float(df_lei['s_testing'].mean()) if not df_lei.empty else 0.0,
                        "s_remedial": float(df_lei['s_remedial'].mean()) if not df_lei.empty else 0.0
                    },
                    "kp_alignment": kp_alignment
                }
            }

            timeline_data = []
            if not df_content.empty:
                df_content['created_at'] = pd.to_datetime(df_content['created_at'])
                df_content['teacher_rating_val'] = df_content['teacher_rating'].apply(lambda x: x.get('score') if isinstance(x, dict) else (json.loads(x).get('score') if (isinstance(x, str) and x) else 0))
                valid_ratings = df_content[df_content['teacher_rating_val'] > 0]
                rq_metrics['rq1']['quality_score'] = float(valid_ratings['teacher_rating_val'].mean()) if not valid_ratings.empty else 0
                
                # Action Type Distribution
                action_counts = df_content['action_type'].fillna('unknown').value_counts().to_dict()
                rq_metrics['rq1']['action_distribution'] = {str(k): int(v) for k, v in action_counts.items()}
                
                # Sort by created_at to calculate regeneration indices
                df_content = df_content.sort_values('created_at')
                session_counts = {}
                
                # --- Pre-compute grouped dictionaries for O(1) lookups ---
                tasks_by_job = {}
                if not df_tasks.empty:
                    for t in df_tasks.to_dict('records'):
                        jid = t.get('job_id')
                        if pd.notna(jid):
                            tasks_by_job.setdefault(int(jid), []).append(t)
                            
                evals_by_job = {}
                if not df_evals.empty:
                    for e in df_evals.to_dict('records'):
                        jid = e.get('job_id')
                        if pd.notna(jid):
                            evals_by_job.setdefault(int(jid), []).append(e)
                            
                prep_by_job = {}
                if not df_prep.empty:
                    for p in df_prep.to_dict('records'):
                        jid = p.get('job_id')
                        if pd.notna(jid):
                            prep_by_job.setdefault(int(jid), []).append(p)

                for _, row in df_content.iterrows():
                    # 1. Start with generation-time metrics
                    initial_ratio = float(row['edit_ratio']) if pd.notna(row['edit_ratio']) else 0.0
                    initial_duration = float(row['edit_duration_seconds']) if pd.notna(row['edit_duration_seconds']) else 0.0
                    
                    # 2. Accumulate from subsequent manual edits
                    manual_ratio = 0.0
                    manual_duration = 0.0
                    history = row['course_edit_history']
                    if history:
                        if isinstance(history, str):
                            try: history = json.loads(history)
                            except: history = []
                        if isinstance(history, list):
                            for h in history:
                                manual_ratio += float(h.get('ratio') or 0)
                                manual_duration += float(h.get('duration') or h.get('edit_duration_seconds') or 0)
                    
                    total_ratio = initial_ratio + manual_ratio
                    total_duration = initial_duration + manual_duration
                                
                    ts_str = str(row['created_at'])
                    is_saved = pd.notna(row['course_content_id'])
                    
                    # 3. Determine regeneration index
                    sid = row['session_id']
                    if sid:
                        session_counts[sid] = session_counts.get(sid, 0) + 1
                        regen_index = session_counts[sid]
                    else:
                        regen_index = 1

                    # 4. Extract RAG & Critic Metrics from df_tasks
                    job_id = row['job_id']
                    rag_metrics = {}
                    critic_scores = {}
                    if pd.notna(job_id):
                        j_inv = int(job_id)
                        job_tasks_list = tasks_by_job.get(j_inv, [])
                        
                        # RAG Metrics from 'retriever'
                        retriever_tasks = [t for t in job_tasks_list if t.get('agent_name') == 'retriever']
                        if retriever_tasks:
                            output = retriever_tasks[0].get('output')
                            if isinstance(output, str):
                                try: output = json.loads(output)
                                except: output = {}
                            if output and ('metrics' in output or 'rag_metrics' in output):
                                m = output.get('metrics') or output.get('rag_metrics')
                                if m:
                                    rag_metrics = {
                                        "keyword_coverage": m.get("keyword_coverage", 0),
                                        "top1_vector_score": m.get("top1_vector_score", 0),
                                        "avg_vector_score": m.get("avg_vector_score", 0),
                                        "bm25_hit_count": m.get("bm25_hit_count", 0),
                                        "diversity_chunks": m.get("diversity_chunks", 0),
                                        "diversity_pages": m.get("diversity_pages", 0),
                                        "quality_assessment": m.get("quality_assessment", "N/A"),
                                        "keyword_hits": m.get("keyword_hits", {}),
                                        "faithfulness": 0
                                    }
                        
                        # Critic Scores from agent_tasks (legacy/backup)
                        quality_tasks = [t for t in job_tasks_list if t.get('agent_name') == 'quality_critic']
                        if quality_tasks:
                            out = quality_tasks[0].get('output')
                            if isinstance(out, str):
                                try: out = json.loads(out)
                                except: out = {}
                            if out and 'evaluations' in out:
                                evals = out['evaluations']
                                for e in evals:
                                    c_name = e.get('criteria')
                                    if c_name:
                                        critic_scores[f"{c_name} (Quality)"] = e.get('rating', 0)
                                critic_scores['quality'] = sum(e.get('rating', 0) for e in evals) / len(evals) if evals else 0
                        
                        # Enrichment from task_evaluations (priority)
                        faith_val = 0
                        job_evals_list = evals_by_job.get(j_inv, [])
                        for ev_row in job_evals_list:
                            m_details = ev_row.get('metric_details')
                            if isinstance(m_details, str):
                                try: m_details = json.loads(m_details)
                                except: m_details = {}
                            
                            if m_details and 'scores' in m_details:
                                q_scores = m_details['scores'].get('quality', {})
                                f_scores = m_details['scores'].get('fact', {})
                                
                                sum_total = 0
                                has_q = False
                                if q_scores:
                                    has_q = True
                                    for crit, val in q_scores.items():
                                        critic_scores[f"{crit} (Quality)"] = val
                                        sum_total += val
                                
                                faith_val = 0
                                if f_scores:
                                    if 'faithfulness' in f_scores:
                                        faith_val = f_scores['faithfulness']
                                        critic_scores['Faithfulness (Fact)'] = faith_val
                                        rag_metrics['faithfulness'] = faith_val
                                    if 'task_satisfaction' in f_scores:
                                        # Still log to critic_scores for detail view, but we won't show in loop
                                        critic_scores['Task Satisfaction (Fact)'] = f_scores['task_satisfaction']
                                
                                # [CORRECTION] AI Quality Assessment should be (Sum of Quality + Faithfulness) / 7
                                if has_q:
                                    critic_scores['quality'] = (sum_total + faith_val) / 7
                        
                        # Factuality from agent_tasks (legacy/fallback)
                        fact_tasks = [t for t in job_tasks_list if t.get('agent_name') == 'fact_critic']
                        if fact_tasks:
                            out = fact_tasks[0].get('output')
                            if isinstance(out, str):
                                try: out = json.loads(out)
                                except: out = {}
                            if out:
                                if 'normalized_score' in out:
                                    critic_scores['Faithfulness (Fact)'] = out['normalized_score']
                                elif 'score' in out:
                                    critic_scores['Faithfulness (Fact)'] = 1 + (out['score'] * 4)
                                
                                if 'task_satisfaction' in out:
                                    ts = out['task_satisfaction']
                                    if isinstance(ts, dict) and 'normalized_score' in ts:
                                        critic_scores['Task Satisfaction (Fact)'] = ts['normalized_score']

                    # 6. Extract input config
                    job_config = row['job_input_config']
                    if isinstance(job_config, str):
                        try: job_config = json.loads(job_config)
                        except: job_config = {}

                    # 5. Behavior Analysis from df_prep
                    prep_stats = {
                        "prep_duration": 0, "mode": "first_gen",
                        "prompt_edit_count": 0, "prompt_edit_duration": 0,
                        "source_preview_count": 0, "source_preview_duration": 0, "unique_sources_previewed": 0,
                        "kp_selection_count": 0, "kp_extracted_count": 0, "kp_manual_count": 0,
                        "kp_interaction_count": 0,
                        "kp_map_view_count": 0, "map_view_duration": 0, "kp_extract_triggered": False,
                        "final_prompt": job_config.get('prompt') if job_config else None
                    }
                    if pd.notna(job_id):
                        j_inv = int(job_id)
                        job_prep_list = prep_by_job.get(j_inv, [])
                        if job_prep_list:
                            prep_row = job_prep_list[0]
                            prep_stats["prep_duration"] = float(prep_row.get('duration_sec')) if pd.notna(prep_row.get('duration_sec')) else 0
                            
                            config = prep_row.get('action_config')
                            if isinstance(config, str):
                                try: config = json.loads(config)
                                except: config = {}
                            
                            actions = config.get('actions', []) if isinstance(config, dict) else []
                            
                            # 1. Prompt Interactions
                            prompt_actions = [a for a in actions if a.get('config', {}).get('action_type') == 'PROMPT_EDIT' or (a.get('config', {}).get('action_type') == 'PARAM_CHANGE' and a.get('config', {}).get('section') == 'prompt')]
                            prep_stats["prompt_edit_count"] = len(prompt_actions)
                            prep_stats["prompt_edit_duration"] = sum(float(a.get('duration_sec') or 0) for a in prompt_actions)
                            
                            # Capture the actual edited prompt if available
                            for a in reversed(actions):
                                a_cfg = a.get('config', {})
                                if a_cfg.get('action_type') == 'PROMPT_EDIT' and a_cfg.get('finalPrompt'):
                                    prep_stats["final_prompt"] = a_cfg.get('finalPrompt')
                                    break
                            
                            # 2. Source Interactions
                            preview_actions = [a for a in actions if a.get('config', {}).get('action_type') == 'MATERIAL_PREVIEW']
                            prep_stats["source_preview_count"] = len(preview_actions)
                            prep_stats["source_preview_duration"] = sum(float(a.get('duration_sec') or 0) for a in preview_actions)
                            preview_keys = [a.get('config', {}).get('key') for a in preview_actions if a.get('config', {}).get('key')]
                            prep_stats["unique_sources_previewed"] = len(set(preview_keys))
                            
                            # 3. KP Interactions
                            selected_kp_names = set()
                            if job_config:
                                ctx = job_config.get('job_context', {})
                                for kp in (ctx.get('knowledge_points') or []): selected_kp_names.add(kp)
                                for kp in (ctx.get('selected_kp_names') or []): selected_kp_names.add(kp)
                            
                            toggle_actions = [a for a in actions if a.get('config', {}).get('action_type') == 'KP_TOGGLE']
                            for a in toggle_actions:
                                name = a.get('config', {}).get('name') or a.get('config', {}).get('key')
                                if a.get('config', {}).get('action') == 'select': 
                                    if name: selected_kp_names.add(name)
                                elif a.get('config', {}).get('action') == 'deselect':
                                    if name in selected_kp_names: selected_kp_names.remove(name)
                            
                            prep_stats["kp_manual_count"] = len([a for a in actions if a.get('config', {}).get('action_type') == 'KP_MANUAL_ADD'])
                            manual_adds = [a for a in actions if a.get('config', {}).get('action_type') == 'KP_MANUAL_ADD']
                            for a in manual_adds:
                                name = a.get('config', {}).get('name')
                                if name: selected_kp_names.add(name)
                            
                            promote_actions = [a for a in actions if a.get('config', {}).get('action_type') in ['KP_PROMOTE', 'KP_PROMOTE_ALL']]
                            kp_ext_count = 0
                            for pa in promote_actions:
                                name = pa.get('config', {}).get('name')
                                if name: selected_kp_names.add(name)
                                count = pa.get('config', {}).get('count', 1)
                                kp_ext_count += count if isinstance(count, int) else 1
                            
                            prep_stats["kp_extracted_count"] = kp_ext_count
                            prep_stats["kp_selection_count"] = len(selected_kp_names)
                            prep_stats["selected_kp_names"] = list(selected_kp_names)

                            # 4. Interaction Count
                            kp_actions = [a for a in actions if a.get('config', {}).get('action_type') in [
                                'KP_TOGGLE', 'KP_MANUAL_ADD', 'KP_DELETE', 'KP_RENAME', 
                                'KP_PROMOTE', 'KP_PROMOTE_ALL', 'KP_SELECT_ALL_UP_TO_LIMIT'
                            ]]
                            prep_stats["kp_interaction_count"] = len(kp_actions)

                            map_open_actions = [a for a in actions if a.get('config', {}).get('action_type') == 'MAP_OPEN' or a.get('config', {}).get('action_type') == 'KNOWLEDGE_MAP_OPEN']
                            prep_stats["kp_map_view_count"] = len(map_open_actions)
                            prep_stats["map_view_duration"] = sum(float(a.get('duration_sec') or 0) for a in [a for a in actions if a.get('config', {}).get('action_type') in ['MAP_CLOSE', 'KNOWLEDGE_MAP_CLOSE']])
                            prep_stats["kp_extract_triggered"] = any(a.get('config', {}).get('action_type') in ['KP_EXTRACT_SUCCESS', 'KP_EXTRACT_EXISTS'] for a in actions)
                            
                            # Mode determination
                            if regen_index > 1:
                                prep_stats["mode"] = "modified_regen" if prep_stats["prompt_edit_count"] > 0 or len([a for a in actions if a.get('config', {}).get('action_type').startswith('KP_')]) > 0 else "direct_regen"
                            else:
                                prep_stats["mode"] = "first_gen"

                    # 7. Determine content tag
                    m_type = job_config.get('job_context', {}).get('material_type') if job_config else None
                    c_type = row.get('content_type')
                    content_tag = "生成內容"
                    if m_type == 'preview': content_tag = "課前預習"
                    elif m_type == 'review': content_tag = "課後複習"
                    elif c_type == 'exam_questions' or (job_config and job_config.get('job_context', {}).get('question_types')): content_tag = "考核測驗"

                    timeline_data.append({
                        'edit_ratio': total_ratio,
                        'edit_duration_seconds': total_duration,
                        'initial_edit_ratio': initial_ratio,
                        'initial_edit_duration': initial_duration,
                        'manual_edit_ratio': manual_ratio,
                        'manual_edit_duration': manual_duration,
                        'source_preview_count': int(row['source_preview_count']) if pd.notna(row['source_preview_count']) else 0,
                        'session_id': sid,
                        'job_id': job_id,
                        'regen_index': regen_index,
                        'created_at': ts_str,
                        'title': row['course_title'] or row['title'] or "未命名內容",
                        'is_saved': is_saved,
                        'course_content_id': int(row['course_content_id']) if pd.notna(row['course_content_id']) else None,
                        'generated_content_id': int(row['id']),
                        'content_tag': content_tag,
                        'teacher_rating': row['teacher_rating_val'],
                        'teacher_rating_data': row['teacher_rating'],
                        'citation_click_count': int(row['source_preview_count']) if pd.notna(row['source_preview_count']) else 0,
                        'rag_metrics': rag_metrics,
                        'critic_scores': critic_scores,
                        'prep_stats': prep_stats,
                        'job_stats': {
                            'used_models': row['used_models'],
                            'total_cost_usd': float(row['total_cost_usd']) if pd.notna(row['total_cost_usd']) else 0,
                            'total_cost_twd': float(row['total_cost_twd']) if pd.notna(row['total_cost_twd']) else 0,
                            'total_tokens': (int(row['total_prompt_tokens']) if pd.notna(row['total_prompt_tokens']) else 0) + 
                                            (int(row['total_completion_tokens']) if pd.notna(row['total_completion_tokens']) else 0),
                            'environmental_impact': row['environmental_impact']
                        },
                        'input_config': job_config
                    })

                rq_metrics['rq1']['edit_efficiency'] = timeline_data
                rq_metrics['rq2']['trust_check'] = timeline_data
                
                # KP Adoption calculation
                df_with_kp = [d for d in timeline_data if d['input_config'] and (d['input_config'].get('selected_kp_ids') or d['input_config'].get('selected_kp_names'))]
                rq_metrics['rq1']['kp_adoption'] = len(df_with_kp) / len(timeline_data) if timeline_data else 0

                # RQ2: Cognitive Load Trend
                if timeline_data:
                    df_long = pd.DataFrame(timeline_data)
                    df_long['created_at'] = pd.to_datetime(df_long['created_at'])
                    df_long['date'] = df_long['created_at'].dt.date.astype(str)
                    cl_trend = df_long.groupby('date').agg({'edit_duration_seconds': 'mean', 'edit_ratio': 'mean'}).reset_index().fillna(0)
                    rq_metrics['rq2']['cognitive_load_trend'] = cl_trend.to_dict('records')
                else:
                    rq_metrics['rq2']['cognitive_load_trend'] = []

            if not df_prep.empty:
                # Group by session_id to see how many tweaks per generation planning
                session_stats = df_prep.groupby('session_id').agg({
                    'duration_sec': 'sum',
                    'id': 'count'
                }).reset_index().fillna(0)
                session_stats.columns = ['session_id', 'total_duration', 'tweak_count']
                rq_metrics['rq2']['prep_efficiency'] = session_stats[['total_duration', 'tweak_count']].to_dict('records')

            if not df_reading.empty:
                df_reading['created_at'] = pd.to_datetime(df_reading['created_at'])
            if not df_questions.empty:
                df_questions['answered_at'] = pd.to_datetime(df_questions['answered_at'])

            if not df_reading.empty and not df_questions.empty:
                # RQ3: SRL Paths
                df_path = pd.merge(df_questions[['unit_session_id', 'correctness', 'answered_at']], 
                                   df_reading[['unit_session_id', 'created_at', 'stay_duration_seconds']], 
                                   on='unit_session_id', how='inner', suffixes=('_q', '_r'))
                if not df_path.empty:
                    df_path['answered_at'] = pd.to_datetime(df_path['answered_at'])
                    df_path['created_at'] = pd.to_datetime(df_path['created_at'])
                    remedial = df_path[(df_path['correctness'] != 'correct') & (df_path['created_at'] > df_path['answered_at'])]
                    rq_metrics['rq3']['remedial_rate'] = float(len(remedial) / len(df_questions)) if len(df_questions) > 0 else 0.0
                
            if not df_reading.empty:
                rq_metrics['rq4']['nav_usage'] = df_reading['exit_action'].value_counts().to_dict()
                # Count total number of interactions across all reading sessions
                interactions_count = df_reading['citation_interactions'].apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
                rq_metrics['rq4']['citation_trust'] = int(interactions_count)

            # --- 彙整統計數據 ---
            teacher_stats = {
                "total_prep": int(len(df_prep)),
                "total_generated": int(len(df_content)),
                "avg_edit_ratio": float(df_content['edit_ratio'].mean()) if (not df_content.empty and pd.notna(df_content['edit_ratio'].mean())) else 0.0,
                "avg_edit_time": float(df_content['edit_duration_seconds'].mean()) if (not df_content.empty and pd.notna(df_content['edit_duration_seconds'].mean())) else 0.0
            }
            
            student_stats = {
                "total_reading": int(len(df_reading)),
                "total_questions": int(len(df_questions)),
                "avg_reading_time": float(df_reading['stay_duration_seconds'].mean()) if (not df_reading.empty and pd.notna(df_reading['stay_duration_seconds'].mean())) else 0.0,
                "avg_scroll_depth": float(df_reading['max_scroll_depth'].mean()) if (not df_reading.empty and pd.notna(df_reading['max_scroll_depth'].mean())) else 0.0,
                "correctness_rate": float((df_questions['correctness'] == 'correct').mean()) if (not df_questions.empty and pd.notna((df_questions['correctness'] == 'correct').mean())) else 0.0
            }

            daily_stats = []
            for i in range(14, -1, -1):
                day = (get_now_taipei() - timedelta(days=i)).date()
                day_str = day.strftime('%Y-%m-%d')
                daily_stats.append({
                    "date": day_str,
                    "t_actions": len(df_content[df_content['created_at'].dt.date == day]) if not df_content.empty else 0,
                    "s_actions": len(df_questions[df_questions['answered_at'].dt.date == day]) if not df_questions.empty else 0
                })

            # Distribution of edit_ratio
            edit_ratio_distribution = []
            if not df_content.empty:
                bins = [0, 0.01, 0.1, 0.3, 0.5, 1.0]
                labels = ["0", "0-0.1", "0.1-0.3", "0.3-0.5", ">0.5"]
                # Ensure edit_ratio has no NaNs for pd.cut
                df_content['edit_ratio'] = df_content['edit_ratio'].fillna(0.0)
                df_content['edit_group'] = pd.cut(df_content['edit_ratio'], bins=bins, labels=labels, include_lowest=True)
                edit_ratio_dist = df_content['edit_group'].value_counts().sort_index().reset_index()
                edit_ratio_dist.columns = ['range', 'count']
                edit_ratio_distribution = edit_ratio_dist.to_dict('records')

            # Reading engagement (Time vs Scroll)
            reading_engagement = []
            if not df_reading.empty:
                # Sample or aggregate to avoid sending too much data
                reading_engagement = df_reading[['stay_duration_seconds', 'max_scroll_depth']].fillna(0).to_dict('records')[:100]

            # Combined Feedback Stats (Reference Feedbacks + Teacher Content Ratings)
            ref_ratings = df_feedback['rating'].tolist() if not df_feedback.empty else []
            teacher_ratings = df_content['teacher_rating_val'].replace(0, np.nan).dropna().tolist() if not df_content.empty else []
            all_ratings = ref_ratings + teacher_ratings
            
            if all_ratings:
                all_ratings_series = pd.Series(all_ratings)
                feedback_stats = {
                    "total_feedbacks": len(all_ratings),
                    "avg_rating": float(all_ratings_series.mean()),
                    "rating_distribution": {str(int(k)): int(v) for k, v in all_ratings_series.value_counts().to_dict().items() if pd.notna(k)}
                }
            else:
                feedback_stats = {
                    "total_feedbacks": 0,
                    "avg_rating": 0.0,
                    "rating_distribution": {}
                }

            # --- Calculate Detailed Summary Metrics ---
            ai_metrics_sum = {}
            ai_metrics_count = {}
            rag_metrics_sum = {
                "keyword_coverage": 0, "top1_vector_score": 0, "avg_vector_score": 0,
                "bm25_hit_count": 0, "faithfulness": 0,
                "diversity_chunks": 0, "diversity_pages": 0
            }
            rag_metrics_count = {k: 0 for k in rag_metrics_sum}
            total_carbon_g = 0
            total_cost_nt = 0
            action_summary = {"save": 0, "regenerate": 0, "discard": 0}

            for d in timeline_data:
                # 1. Action Counts
                if d.get('is_saved'):
                    action_summary["save"] += 1
                else:
                    prep_stats = d.get('prep_stats') or {}
                    job_stats = d.get('job_stats') or {}
                    act = prep_stats.get('action_type') or job_stats.get('action_type')
                    if act == 'regenerate':
                        action_summary["regenerate"] += 1
                    else:
                        action_summary["discard"] += 1

                # 2. AI Metrics Aggregation (Critic)
                scores = d.get('critic_scores', {})
                for k, v in scores.items():
                    kl = k.lower()
                    if kl in ['quality', 'quality_avg']: continue
                    if 'faithfulness' in kl or 'task satisfaction' in kl: continue
                    
                    # Normalize naming variations (e.g. merge Grammatical & Fluency)
                    norm_k = k
                    if "Grammatical" in k or "Fluency" in k:
                        norm_k = "語法正確性 (Grammatical)"
                        
                    ai_metrics_sum[norm_k] = ai_metrics_sum.get(norm_k, 0) + v
                    ai_metrics_count[norm_k] = ai_metrics_count.get(norm_k, 0) + 1
                
                # 3. RAG Metrics Aggregation
                rag_m = d.get('rag_metrics', {})
                if rag_m:
                    for k in rag_metrics_sum:
                        if k in rag_m and rag_m[k] is not None:
                            rag_metrics_sum[k] += rag_m[k]
                            rag_metrics_count[k] += 1

                # 4. Environmental & Cost
                stats = d.get('job_stats') or {}
                total_cost_nt += stats.get('total_cost_twd', 0)
                impact = stats.get('environmental_impact')
                if impact:
                    if isinstance(impact, str):
                        try: impact = json.loads(impact)
                        except: impact = {}
                    if isinstance(impact, dict):
                        total_carbon_g += impact.get('carbon_g', 0)

            def _safe_float(v):
                if v is None or pd.isna(v) or np.isinf(v): return 0.0
                return float(v)

            summarized_metrics = {
                "ai_averages": {k: _safe_float(ai_metrics_sum[k] / ai_metrics_count[k]) for k in ai_metrics_sum if ai_metrics_count[k] > 0},
                "rag_averages": {k: _safe_float(rag_metrics_sum[k] / rag_metrics_count[k]) for k in rag_metrics_sum if rag_metrics_count[k] > 0},
                "total_cost_nt": _safe_float(total_cost_nt),
                "total_carbon_g": _safe_float(total_carbon_g),
                "action_summary": action_summary,
                "total_generations": len(timeline_data),
                "avg_edit_ratio": _safe_float(teacher_stats["avg_edit_ratio"]),
                "avg_edit_time": _safe_float(teacher_stats["avg_edit_time"])
            }

            return {
                "teacher_stats": teacher_stats,
                "student_stats": student_stats,
                "daily_stats": daily_stats,
                "edit_ratio_distribution": edit_ratio_distribution,
                "reading_engagement": reading_engagement,
                "feedback_stats": feedback_stats,
                "rq_metrics": rq_metrics,
                "kp_source_types": kp_source_types,
                "summarized_metrics": summarized_metrics
            }

    return await run_in_db_pool(_sync_experiment_stats, course_id, unit_id, days)

@router.post("/experiment/seeds", dependencies=[Depends(require_admin)])
async def extract_and_save_seed(request: SeedExtractRequest):
    """將指定的 Job Config 提取並儲存為實驗種子 (exp_seed_configs)"""
    def _sync_extract_seed(job_id):
        import json
        from sqlalchemy import text as sql_text
        with engine.begin() as conn:
            # 1. 取得設定日誌及原設定檔
            res = conn.execute(sql_text("""
                SELECT g.user_id, oj.input_config
                FROM generator_setting_logs g
                JOIN orchestration_jobs oj ON g.job_id = oj.id
                WHERE g.job_id = :job_id
            """), {"job_id": job_id}).fetchone()
            
            if not res:
                return None, "找不到對應的設定紀錄"
                
            user_id = res[0] or 1
            input_config = res[1] or {}
            if isinstance(input_config, str):
                try: input_config = json.loads(input_config)
                except: input_config = {}
                
            context = input_config.get('job_context', {})
            
            seed_config = {
                "user_id": user_id,
                "prompt": input_config.get('original_prompt', ''),
                "content_type": "material" if context.get("material_type") else "exam_questions",
                "source_ids": context.get("source_ids", []),
                "generated_source_ids": context.get("generated_ids", []),
                "selected_kp_ids": context.get("selected_kp_ids", []),
                "selected_kp_names": context.get("selected_kp_names", []),
                "unit_id": context.get("unit_id"),
                "material_type": context.get("material_type"),
                "length": context.get("length", "standard"),
                "question_types": context.get("question_types"),
                "question_count": context.get("question_count", 5),
                "model_name": input_config.get("experiment_config", {}).get("modelName", "gpt-4o-mini")
            }
            
            # 過濾掉 None 值
            seed_config = {k: v for k, v in seed_config.items() if v is not None}
            
            # 2. 獲取可能關聯的課程名稱
            course_name = "Experiment Course"
            course_id = context.get("course_id")
            if course_id:
                c_res = conn.execute(sql_text("SELECT name FROM courses WHERE id = :cid"), {"cid": course_id}).fetchone()
                if c_res: course_name = c_res[0]
                
            unit_id = context.get("unit_id") or 1
            
            # 3. 檢查是否已經存在相同 original_job_id 的 seed
            check_res = conn.execute(sql_text("SELECT id FROM exp_seed_configs WHERE original_job_id = :jid"), {"jid": job_id}).fetchone()
            if check_res:
                return {"seed_id": check_res[0]}, "此設定檔已經存在於實驗種子中"
                
            # 4. 插入 exp_seed_configs
            insert_res = conn.execute(sql_text("""
                INSERT INTO exp_seed_configs (course_name, unit_id, input_config, original_job_id)
                VALUES (:course_name, :unit_id, :input_config, :original_job_id)
                RETURNING id
            """), {
                "course_name": course_name,
                "unit_id": unit_id,
                "input_config": json.dumps(seed_config),
                "original_job_id": job_id
            })
            
            seed_id = insert_res.scalar()
            return {"seed_id": seed_id}, None
            
    result, error = await run_in_db_pool(_sync_extract_seed, request.job_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
        
    return {"message": "成功加入實驗種子庫", "data": result}
