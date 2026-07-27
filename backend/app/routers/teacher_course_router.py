"""
Teacher Course Router: 整合教師與課程相關的 API
處理課程管理、單元管理、公告管理以及教師課程列表
"""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
import json
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any, Union, Tuple
from sqlalchemy import Table, text
from backend.app.utils.db_logger import engine, metadata
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id

logger = logging.getLogger(__name__)

# 建立 Router (不設定統一 prefix，因為要處理 /api/courses 和 /api/teachers)
router = APIRouter()

# 反射資料表 (保留供參考或未來使用)
try:
    courses_table = Table('courses', metadata, autoload_with=engine)
    course_units_table = Table('course_units', metadata, autoload_with=engine)
    users_table = Table('users', metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting course tables: {e}")

# ==================== Pydantic Schemas ====================

class CourseResponse(BaseModel):
    """一般課程回應"""
    id: int
    name: str
    semester: str  # 統一欄位名稱 (原 semester_name)
    description: Optional[str] = None
    teacher_name: str

class CourseUnitResponse(BaseModel):
    """課程單元回應"""
    id: int
    topic_id: Optional[int] = 0
    name: str
    description: Optional[str] = None
    attachments: List[Dict[str, Any]] = []

class CourseDetailResponse(BaseModel):
    """課程詳情回應（含單元）"""
    id: int
    name: str
    semester: str # 統一欄位名稱
    description: Optional[str] = None
    teacher_name: str
    teacher_email: Optional[str] = None
    teacher_department: Optional[str] = None
    units: List[CourseUnitResponse]

class AnnouncementCreate(BaseModel):
    """建立公告的請求"""
    title: str
    content: str
    author_id: Optional[int] = None
    is_pinned: Optional[bool] = False
    is_visible: Optional[bool] = True

class AnnouncementUpdate(BaseModel):
    """更新公告的請求"""
    title: Optional[str] = None
    content: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_visible: Optional[bool] = None

class AnnouncementResponse(BaseModel):
    """公告回應"""
    id: int
    title: str
    content: str
    is_pinned: bool
    is_visible: bool
    created_at: str
    author_name: str

class UnitCreate(BaseModel):
    """建立課程單元的請求"""
    topic_id: int
    name: str
    description: Optional[str] = None

# ==================== API Endpoints (Courses) ====================

def _sync_get_all_courses():
    with engine.connect() as conn:
        query = text("""
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            WHERE c.is_deleted = FALSE
            ORDER BY c.created_at DESC
        """)
        result = conn.execute(query)
        
        courses = []
        for row in result:
            courses.append({
                "id": row[0],
                "name": row[1],
                "semester": row[2],
                "description": row[3],
                "teacher_name": row[4] or "未知教師"
            })
        return courses

@router.get("/api/courses", response_model=List[CourseResponse], tags=["Courses"])
async def get_all_courses():
    """
    取得所有課程列表
    """
    courses_data = await run_in_db_pool(_sync_get_all_courses)
    return [CourseResponse(**c) for c in courses_data]

class CourseCreate(BaseModel):
    """建立課程請求"""
    name: str
    semester_name: str
    description: Optional[str] = None
    teacher_id: int

def _sync_create_course(course_data: dict):
    with engine.connect() as conn:
        # 1. 確認教師存在
        user_check = conn.execute(
            text("SELECT id FROM users WHERE id = :user_id"), 
            {"user_id": course_data["teacher_id"]}
        ).fetchone()
        
        if not user_check:
            return None, "Teacher not found"

        # 2. 插入課程
        insert_query = text("""
            INSERT INTO courses (name, semester_name, description, teacher_id, created_at)
            VALUES (:name, :semester_name, :description, :teacher_id, :created_at)
            RETURNING id, name, semester_name, description
        """)
        result = conn.execute(insert_query, {
            "name": course_data["name"],
            "semester_name": course_data["semester_name"],
            "description": course_data["description"] or "",
            "teacher_id": course_data["teacher_id"],
            "created_at": get_now_taipei()
        })
        conn.commit()
        row = result.fetchone()
        
        # 3. 创建默认章节 "課堂簡介"
        default_unit_query = text("""
            INSERT INTO course_units (course_id, topic_id, name, description)
            VALUES (:course_id, 1, '課堂簡介', '本章節為課程簡介，教師可自行修改內容')
        """)
        conn.execute(default_unit_query, {"course_id": row[0]})
        conn.commit()
        
        # 4. 取得教師名稱
        teacher_name_query = text("SELECT full_name FROM users WHERE id = :id")
        teacher_name_res = conn.execute(teacher_name_query, {"id": course_data["teacher_id"]}).fetchone()
        teacher_name = teacher_name_res[0] if teacher_name_res else "未知教師"

        return {
            "id": row[0],
            "name": row[1],
            "semester": row[2],
            "description": row[3],
            "teacher_name": teacher_name
        }, None

@router.post("/api/courses", response_model=CourseResponse, tags=["Courses"])
async def create_course(course: CourseCreate):
    """
    建立新課程
    """
    course_dict = course.dict()
    result, error = await run_in_db_pool(_sync_create_course, course_dict)
    
    if error == "Teacher not found":
        raise HTTPException(status_code=404, detail="教師不存在")
    elif error:
        raise HTTPException(status_code=500, detail=error)
        
    return CourseResponse(**result)

def _sync_delete_course(course_id: int):
    with engine.connect() as conn:
        # 檢查課程是否存在
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return False
        
        # 軟刪除課程 (及時關聯資料保留，僅隱藏)
        delete_query = text("UPDATE courses SET is_deleted = TRUE WHERE id = :course_id")
        conn.execute(delete_query, {"course_id": course_id})
        conn.commit()
        return True

@router.delete("/api/courses/{course_id}", tags=["Courses"])
async def delete_course(course_id: int):
    """
    刪除課程
    """
    success = await run_in_db_pool(_sync_delete_course, course_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="課程不存在")
    
    logger.info(f"✅ Successfully deleted course: ID={course_id}")
    return {"message": "課程已刪除"}


def _sync_get_course_detail(course_id: int):
    with engine.connect() as conn:
        course_query = text("""
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name,
                   u.email as teacher_email, tp.institution as teacher_department
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            LEFT JOIN teacher_profiles tp ON tp.user_id = u.id
            WHERE c.id = :course_id
        """)
        course_result = conn.execute(course_query, {"course_id": course_id}).fetchone()
        
        if not course_result:
            return None
        
        units_query = text("""
            SELECT id, topic_id, name, description
            FROM course_units
            WHERE course_id = :course_id
            ORDER BY topic_id ASC
        """)
        units_result = conn.execute(units_query, {"course_id": course_id})
        
        units_data = []
        unit_ids = []
        for row in units_result:
            units_data.append({
                "id": row[0],
                "topic_id": row[1],
                "name": row[2],
                "description": row[3],
                "attachments": []
            })
            unit_ids.append(row[0])
            
        # 批量查詢附件 (Eager Loading)
        if unit_ids:
            attachments_query = text("""
                SELECT id, attachable_id, file_name, original_file_name, file_size_bytes, 
                       file_type, uploaded_at
                FROM attachments 
                WHERE attachable_type IN ('material', 'unit') AND attachable_id IN :unit_ids
                ORDER BY uploaded_at DESC
            """)
            # SQLAlchemy handles list parameter binding for IN clause
            attachments_result = conn.execute(attachments_query, {"unit_ids": tuple(unit_ids)})
            
            attachments_map = {}
            for row in attachments_result:
                unit_id = row[1]
                if unit_id not in attachments_map:
                    attachments_map[unit_id] = []
                
                from datetime import timezone, timedelta
                dt = row[6]
                uploaded_at_str = ""
                if dt:
                    if dt.tzinfo:
                        uploaded_at_str = dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
                    else:
                        taipei_tz = timezone(timedelta(hours=8))
                        uploaded_at_str = dt.replace(tzinfo=taipei_tz).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

                attachments_map[unit_id].append({
                    "id": row[0],
                    "file_name": row[2],
                    "original_file_name": row[3],
                    "file_size_bytes": row[4],
                    "file_type": row[5],
                    "uploaded_at": uploaded_at_str,
                    # Construct download URL
                    "download_url": f"/api/attachments/{row[0]}/download"
                })
            
            # 將附件填回對應單元
            for unit in units_data:
                if unit["id"] in attachments_map:
                    unit["attachments"] = attachments_map[unit["id"]]

        return {
            "id": course_result[0],
            "name": course_result[1],
            "semester": course_result[2],
            "description": course_result[3],
            "teacher_name": course_result[4] or "未知教師",
            "teacher_email": course_result[5],
            "teacher_department": course_result[6],
            "units": units_data
        }

@router.get("/api/courses/{course_id}", response_model=CourseDetailResponse, tags=["Courses"])
async def get_course_detail(course_id: int):
    """
    取得單一課程詳情（含週次單元及附件）
    """
    result = await run_in_db_pool(_sync_get_course_detail, course_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="課程不存在")
        
    return CourseDetailResponse(
        id=result["id"],
        name=result["name"],
        semester=result["semester"],
        description=result["description"],
        teacher_name=result["teacher_name"],
        teacher_email=result["teacher_email"],
        teacher_department=result["teacher_department"],
        units=[CourseUnitResponse(**u) for u in result["units"]]
    )

def _sync_get_course_units(course_id: int):
    with engine.connect() as conn:
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return None
        
        query = text("""
            SELECT id, topic_id, name, description
            FROM course_units
            WHERE course_id = :course_id
            ORDER BY topic_id ASC
        """)
        result = conn.execute(query, {"course_id": course_id})
        
        units = []
        for row in result:
            units.append({
                "id": row[0],
                "topic_id": row[1],
                "name": row[2],
                "description": row[3]
            })
        return units

@router.get("/api/courses/{course_id}/units", response_model=List[CourseUnitResponse], tags=["Courses"])
async def get_course_units(course_id: int):
    """
    取得課程的所有週次單元
    """
    units_data = await run_in_db_pool(_sync_get_course_units, course_id)
    
    if units_data is None:
        raise HTTPException(status_code=404, detail="課程不存在")
        
    return [CourseUnitResponse(**u) for u in units_data]

def _sync_create_course_unit(course_id: int, unit_data: dict):
    with engine.connect() as conn:
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return None, "Course not found"
        
        insert_query = text("""
            INSERT INTO course_units (course_id, topic_id, name, description, updated_at)
            VALUES (:course_id, :topic_id, :name, :description, :updated_at)
            RETURNING id, topic_id, name
        """)
        result = conn.execute(insert_query, {
            "course_id": course_id,
            "topic_id": unit_data["topic_id"],
            "name": unit_data["name"],
            "description": unit_data["description"] or "",
            "updated_at": get_now_taipei()
        })
        conn.commit()
        
        row = result.fetchone()
        return {
            "id": row[0],
            "topic_id": row[1],
            "name": row[2],
            "description": None
        }, None

@router.post("/api/courses/{course_id}/units", response_model=CourseUnitResponse, tags=["Courses"])
async def create_course_unit(course_id: int, unit: UnitCreate):
    """
    建立新課程單元
    """
    unit_dict = unit.dict()
    result, error = await run_in_db_pool(_sync_create_course_unit, course_id, unit_dict)
    
    if error == "Course not found":
        raise HTTPException(status_code=404, detail="課程不存在")
    elif error:
        raise HTTPException(status_code=500, detail=error)
        
    logger.info(f"✅ Successfully created course unit: ID={result['id']}, Topic={result['topic_id']}, Name='{result['name']}', Course={course_id}")
    return CourseUnitResponse(**result)

def _sync_delete_course_unit(course_id: int, unit_id: int):
    with engine.connect() as conn:
        check_query = text("""
            SELECT id FROM course_units 
            WHERE id = :unit_id AND course_id = :course_id
        """)
        unit = conn.execute(check_query, {
            "unit_id": unit_id,
            "course_id": course_id
        }).fetchone()
        
        if not unit:
            return False
        
        # 1. 刪除關聯的附件檔案和記錄
        from pathlib import Path
        attachments_query = text("""
            SELECT id, file_path 
            FROM attachments 
            WHERE attachable_type IN ('material', 'unit') AND attachable_id = :unit_id
        """)
        attachments = conn.execute(attachments_query, {"unit_id": unit_id}).fetchall()
        
        # 刪除實體檔案
        for att in attachments:
            try:
                file_path = Path(att.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete attachment file {att.file_path}: {e}")
        
        # 刪除附件資料庫記錄
        if attachments:
            conn.execute(text("DELETE FROM attachments WHERE attachable_type IN ('material', 'unit') AND attachable_id = :unit_id"), 
                         {"unit_id": unit_id})

        # 2. 刪除單元本身
        conn.execute(text("DELETE FROM course_units WHERE id = :unit_id"), {"unit_id": unit_id})
        conn.commit()
        return True

@router.delete("/api/courses/{course_id}/units/{unit_id}", tags=["Courses"])
async def delete_course_unit(course_id: int, unit_id: int):
    """
    刪除課程單元
    """
    success = await run_in_db_pool(_sync_delete_course_unit, course_id, unit_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="課程單元不存在")
        
    return {"message": "課程單元已刪除"}

def _sync_update_course_unit(course_id: int, unit_id: int, unit_data: dict):
    with engine.connect() as conn:
        # 檢查單元是否存在
        check_query = text("""
            SELECT id FROM course_units 
            WHERE id = :unit_id AND course_id = :course_id
        """)
        existing = conn.execute(check_query, {
            "unit_id": unit_id,
            "course_id": course_id
        }).fetchone()
        
        if not existing:
            return None
        
        # 更新單元
        update_query = text("""
            UPDATE course_units 
            SET topic_id = :topic_id, name = :name, description = :description, 
                updated_at = :updated_at
            WHERE id = :unit_id
            RETURNING id, topic_id, name, description
        """)
        result = conn.execute(update_query, {
            "unit_id": unit_id,
            "topic_id": unit_data["topic_id"],
            "name": unit_data["name"],
            "description": unit_data["description"] or "",
            "updated_at": get_now_taipei()
        })
        conn.commit()
        
        row = result.fetchone()
        return {
            "id": row[0],
            "topic_id": row[1],
            "name": row[2],
            "description": row[3]
        }

@router.put("/api/courses/{course_id}/units/{unit_id}", response_model=CourseUnitResponse, tags=["Courses"])
async def update_course_unit(course_id: int, unit_id: int, unit: UnitCreate):
    """
    更新課程單元
    """
    unit_dict = unit.dict()
    result = await run_in_db_pool(_sync_update_course_unit, course_id, unit_id, unit_dict)
    
    if not result:
        raise HTTPException(status_code=404, detail="課程單元不存在")
        
    logger.info(f"✅ Successfully updated course unit: ID={result['id']}, Topic={result['topic_id']}, Name='{result['name']}'")
    return CourseUnitResponse(**result)

# ==================== Announcements ====================

def _sync_get_course_announcements(course_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT a.id, a.title, a.content, a.is_pinned, a.is_visible, a.created_at, u.full_name
            FROM course_announcements a
            LEFT JOIN users u ON a.author_id = u.id
            WHERE a.course_id = :course_id
            ORDER BY a.is_pinned DESC, a.updated_at DESC
        """)
        result = conn.execute(query, {"course_id": course_id})
        
        announcements = []
        for row in result:
            announcements.append({
                "id": row[0],
                "title": row[1],
                "content": row[2],
                "is_pinned": row[3],
                "is_visible": row[4],
                "created_at": row[5].isoformat() if row[5] else "",
                "author_name": row[6] or "未知"
            })
        return announcements

@router.get("/api/courses/{course_id}/announcements", response_model=List[AnnouncementResponse], tags=["Courses"])
async def get_course_announcements(course_id: int):
    """
    取得課程的所有公告
    """
    announcements_data = await run_in_db_pool(_sync_get_course_announcements, course_id)
    return [AnnouncementResponse(**a) for a in announcements_data]

def _sync_create_announcement(course_id: int, announcement_data: dict):
    with engine.connect() as conn:
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return None, "Course not found"
        
        # 優先使用傳入的 author_id (通常來自 JWT token)
        author_id = announcement_data.get("author_id")
        
        if not author_id:
            teacher_query = text("SELECT teacher_id FROM courses WHERE id = :course_id")
            teacher_result = conn.execute(teacher_query, {"course_id": course_id}).fetchone()
            author_id = teacher_result[0] if teacher_result else 1
        
        insert_query = text("""
            INSERT INTO course_announcements (course_id, author_id, title, content, is_pinned, is_visible, created_at, updated_at)
            VALUES (:course_id, :author_id, :title, :content, :is_pinned, :is_visible, :created_at, :updated_at)
            RETURNING id, title, content, is_pinned, is_visible, created_at
        """)
        now = get_now_taipei()
        result = conn.execute(insert_query, {
            "course_id": course_id,
            "author_id": author_id,
            "title": announcement_data["title"],
            "content": announcement_data["content"],
            "is_pinned": announcement_data.get("is_pinned", False),
            "is_visible": announcement_data.get("is_visible", True),
            "created_at": now,
            "updated_at": now
        })
        conn.commit()
        
        row = result.fetchone()
        
        author_query = text("SELECT full_name FROM users WHERE id = :author_id")
        author_result = conn.execute(author_query, {"author_id": author_id}).fetchone()
        
        return {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "is_pinned": row[3],
            "is_visible": row[4],
            "created_at": row[5].isoformat() if row[5] else "",
            "author_name": author_result[0] if author_result else "未知"
        }, None

@router.post("/api/courses/{course_id}/announcements", response_model=AnnouncementResponse, tags=["Courses"])
async def create_announcement(course_id: int, announcement: AnnouncementCreate, current_user_id: int = Depends(get_current_user_id)):
    """
    建立新公告
    """
    announcement_dict = announcement.dict()
    # 如果 Request Body 中沒有帶 author_id，則從 Token 提取
    if not announcement_dict.get("author_id"):
        announcement_dict["author_id"] = current_user_id
        
    result, error = await run_in_db_pool(_sync_create_announcement, course_id, announcement_dict)
    
    if error == "Course not found":
        raise HTTPException(status_code=404, detail="課程不存在")
    elif error:
        raise HTTPException(status_code=500, detail=error)
        
    logger.info(f"✅ Successfully created announcement: ID={result['id']}, Title='{result['title']}', Course={course_id}")
    return AnnouncementResponse(**result)

def _sync_delete_announcement(course_id: int, announcement_id: int):
    with engine.connect() as conn:
        check_query = text("""
            SELECT id FROM course_announcements 
            WHERE id = :announcement_id AND course_id = :course_id
        """)
        announcement = conn.execute(check_query, {
            "announcement_id": announcement_id,
            "course_id": course_id
        }).fetchone()
        
        if not announcement:
            return False
        
        # 1. 刪除關聯的附件檔案和記錄
        from pathlib import Path
        attachments_query = text("""
            SELECT id, file_path 
            FROM attachments 
            WHERE attachable_type = 'announcement' AND attachable_id = :announcement_id
        """)
        attachments = conn.execute(attachments_query, {"announcement_id": announcement_id}).fetchall()
        
        # 刪除實體檔案
        for att in attachments:
            try:
                file_path = Path(att.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete attachment file {att.file_path}: {e}")
        
        # 刪除附件資料庫記錄
        if attachments:
            conn.execute(text("DELETE FROM attachments WHERE attachable_type = 'announcement' AND attachable_id = :announcement_id"), 
                         {"announcement_id": announcement_id})

        # 2. 刪除公告本身
        conn.execute(text("DELETE FROM course_announcements WHERE id = :announcement_id"), {"announcement_id": announcement_id})
        conn.commit()
        return True

@router.delete("/api/courses/{course_id}/announcements/{announcement_id}", tags=["Courses"])
async def delete_announcement(course_id: int, announcement_id: int):
    """
    刪除公告（連同附件一起刪除）
    """
    success = await run_in_db_pool(_sync_delete_announcement, course_id, announcement_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="公告不存在")
        
    return {"message": "公告及附件已刪除"}


def _sync_update_announcement(course_id: int, announcement_id: int, announcement_data: dict):
    with engine.connect() as conn:
        # 檢查公告是否存在
        check_query = text("""
            SELECT id, author_id FROM course_announcements 
            WHERE id = :announcement_id AND course_id = :course_id
        """)
        existing = conn.execute(check_query, {
            "announcement_id": announcement_id,
            "course_id": course_id
        }).fetchone()
        
        if not existing:
            return None
        
        author_id = existing[1]
        
        # 更新公告
        update_fields = []
        params = {"announcement_id": announcement_id}
        
        if "title" in announcement_data and announcement_data["title"] is not None:
            update_fields.append("title = :title")
            params["title"] = announcement_data["title"]
        if "content" in announcement_data and announcement_data["content"] is not None:
            update_fields.append("content = :content")
            params["content"] = announcement_data["content"]
        if "is_pinned" in announcement_data and announcement_data["is_pinned"] is not None:
            update_fields.append("is_pinned = :is_pinned")
            params["is_pinned"] = announcement_data["is_pinned"]
        if "is_visible" in announcement_data and announcement_data["is_visible"] is not None:
            update_fields.append("is_visible = :is_visible")
            params["is_visible"] = announcement_data["is_visible"]
            
        if not update_fields:
            return None # Nothing to update
            
        update_fields.append("updated_at = :updated_at")
        params["updated_at"] = get_now_taipei()
        
        update_query = text(f"""
            UPDATE course_announcements 
            SET {", ".join(update_fields)}
            WHERE id = :announcement_id
            RETURNING id, title, content, is_pinned, is_visible, created_at
        """)
        result = conn.execute(update_query, params)
        conn.commit()
        
        row = result.fetchone()
        if not row:
            return None
            
        # 取得作者名稱
        author_query = text("SELECT full_name FROM users WHERE id = :author_id")
        author_result = conn.execute(author_query, {"author_id": author_id}).fetchone()
        
        return {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "is_pinned": row[3],
            "is_visible": row[4],
            "created_at": row[5].isoformat() if row[5] else "",
            "author_name": author_result[0] if author_result else "未知"
        }

@router.put("/api/courses/{course_id}/announcements/{announcement_id}", response_model=AnnouncementResponse, tags=["Courses"])
async def update_announcement(course_id: int, announcement_id: int, announcement: AnnouncementUpdate):
    """
    更新公告 (包含置頂與可見性)
    """
    announcement_dict = announcement.dict(exclude_unset=True)
    result = await run_in_db_pool(_sync_update_announcement, course_id, announcement_id, announcement_dict)
    
    if not result:
        raise HTTPException(status_code=404, detail="公告不存在或無更新內容")
        
    logger.info(f"✅ Successfully updated announcement: ID={result['id']}, Title='{result['title']}'")
    
    return AnnouncementResponse(**result)


# ==================== API Endpoints (Teachers) ====================

def _sync_get_teacher_courses(teacher_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            WHERE (c.teacher_id = :teacher_id OR c.id IN (
                SELECT course_id FROM enrollments WHERE user_id = :teacher_id AND role = 'ta'
            )) AND c.is_deleted = FALSE
            ORDER BY c.created_at DESC
        """)
        result = conn.execute(query, {"teacher_id": teacher_id})
        
        courses = []
        for row in result:
            courses.append({
                "id": row[0],
                "name": row[1],
                "semester": row[2],
                "description": row[3],
                "teacher_name": row[4] or "未知教師"
            })
        return courses

@router.get("/api/teachers/{teacher_id}/courses", response_model=List[CourseResponse], tags=["Teachers"])
async def get_teacher_courses(teacher_id: int):
    """
    取得特定教師開設的所有課程列表 (排除已刪除)
    """
    courses_data = await run_in_db_pool(_sync_get_teacher_courses, teacher_id)
    return [CourseResponse(**c) for c in courses_data]

# ==================== Soft Delete / Restore Endpoints ====================

def _sync_restore_course(course_id: int):
    with engine.connect() as conn:
        # 檢查課程是否存在
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :course_id"),
            {"course_id": course_id}
        ).fetchone()
        
        if not course_check:
            return False
        
        # 恢復課程
        restore_query = text("UPDATE courses SET is_deleted = FALSE WHERE id = :course_id")
        conn.execute(restore_query, {"course_id": course_id})
        conn.commit()
        return True

@router.post("/api/courses/{course_id}/restore", tags=["Courses"])
async def restore_course(course_id: int):
    """
    恢復已刪除的課程
    """
    success = await run_in_db_pool(_sync_restore_course, course_id)
    if not success:
        raise HTTPException(status_code=404, detail="課程不存在")
    
    logger.info(f"✅ Successfully restored course: ID={course_id}")
    return {"message": "課程已恢復"}

def _sync_get_deleted_courses(teacher_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT c.id, c.name, c.semester_name, c.description, u.full_name as teacher_name
            FROM courses c
            LEFT JOIN users u ON c.teacher_id = u.id
            WHERE c.teacher_id = :teacher_id AND c.is_deleted = TRUE
            ORDER BY c.created_at DESC
        """)
        result = conn.execute(query, {"teacher_id": teacher_id})
        
        courses = []
        for row in result:
            courses.append({
                "id": row[0],
                "name": row[1],
                "semester": row[2],
                "description": row[3],
                "teacher_name": row[4] or "未知教師"
            })
        return courses

@router.get("/api/teachers/{teacher_id}/deleted-courses", response_model=List[CourseResponse], tags=["Teachers"])
async def get_deleted_courses(teacher_id: int):
    """
    取得特定教師已刪除的課程列表 (用於復原)
    """
    courses_data = await run_in_db_pool(_sync_get_deleted_courses, teacher_id)
    return [CourseResponse(**c) for c in courses_data]

# ==================== Content Creation Schemas ====================

# ==================== Content Management Schemas ====================

class KPItem(BaseModel):
    name: str
    level: Optional[str] = 'sub_technique'

class ContentCreate(BaseModel):
    """統一內容建立請求"""
    title: str
    content_type: str # material, exam
    content_subtype: Optional[str] = None  # preview/review (教材) 或 quiz/homework/midterm/final (試卷)
    source_type: str # generated_content, uploaded_content, text, url
    source_id: int
    source_ids: Optional[List[int]] = None # ✅ New: Multiple source tracking
    unit_id: Optional[int] = None
    content: Optional[Any] = None # JSON content (questions, text, etc)
    
    # Grading related (optional)
    include_in_grade: bool = False
    weight: float = 0.0
    total_points: float = 100.0
    question_grading: Optional[Dict[str, Any]] = None # For exams
    
    # KP Linking
    selected_kp_names: List[str] = []  # Deprecated but kept for compatibility
    selected_kps: List[KPItem] = []    # ✅ New: Structured KP list with levels
    
    # Publishing settings
    is_visible: bool = True
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Exam-specific timing
    duration_minutes: Optional[int] = None
    allow_review: bool = True
    show_answers_after: Optional[datetime] = None
    
    # File upload assignment (only meaningful for exam/assignment type)
    assignment_type: Optional[str] = None  # 'questions' or 'file_upload'; NULL for material
    description: Optional[str] = None  # Assignment description (Markdown)
    
    # Other
    author_id: Optional[int] = None
    edit_duration_seconds: Optional[int] = 0  # 編輯所花費的時間 (秒)
    
    @validator('content_type')
    def validate_content_type(cls, v):
        allowed = ['material', 'exam']
        if v not in allowed:
            raise ValueError(f"content_type 必須是 {allowed} 之一，不再支援 'assignment'")
        return v
    
    @validator('end_time')
    def validate_end_time(cls, v, values):
        if v and 'start_time' in values and values['start_time']:
            if v <= values['start_time']:
                raise ValueError('end_time 必須晚於 start_time')
        return v
    

class ContentUpdate(BaseModel):
    """統一內容更新請求"""
    title: Optional[str] = None
    content_type: Optional[str] = None
    content_subtype: Optional[str] = None
    content: Optional[Any] = None
    
    # Grading
    include_in_grade: Optional[bool] = None
    weight: Optional[float] = None
    total_points: Optional[float] = None
    question_grading: Optional[Dict[str, Any]] = None
    
    # Publishing settings
    is_visible: Optional[bool] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Exam-specific
    duration_minutes: Optional[int] = None
    allow_review: Optional[bool] = None
    show_answers_after: Optional[datetime] = None
    
    # File upload assignment
    assignment_type: Optional[str] = None  # 'questions' or 'file_upload'
    description: Optional[str] = None  # Assignment description (Markdown)
    
    # Other
    unit_id: Optional[int] = None
    selected_kp_names: Optional[List[str]] = None
    kp_id: Optional[Union[int, str]] = None
    source_ids: Optional[List[int]] = None
    edit_duration_seconds: Optional[int] = None  # 本次編輯增加的時間

class ContentResponse(BaseModel):
    id: int
    course_id: int
    unit_id: Optional[int]
    title: str
    content_type: str
    source_type: str
    source_id: int
    source_ids: Optional[List[int]] = None
    content: Optional[Any]
    
    include_in_grade: bool
    weight: float
    total_points: float
    question_grading: Optional[Dict[str, Any]]
    
    # Publishing settings
    is_visible: bool
    content_subtype: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    allow_review: Optional[bool] = None
    show_answers_after: Optional[datetime] = None
    assignment_type: Optional[str] = None  # 'questions' or 'file_upload'; NULL for material
    description: Optional[str] = None  # 作業說明（Markdown）
    
    created_at: str
    job_id: Optional[int] = None
    display_order: Optional[int] = 0

class ContentListResponse(BaseModel):
    """列表用的簡化 Schema（不含 content）"""
    id: int
    course_id: int
    unit_id: Optional[int]
    title: str
    content_type: str
    content_subtype: Optional[str] = None
    source_type: str
    source_id: int
    source_ids: Optional[List[int]] = None
    # ❌ 沒有 content 欄位
    
    include_in_grade: bool
    weight: float
    total_points: float
    
    is_visible: bool
    created_at: str
    job_id: Optional[int] = None
    assignment_type: Optional[str] = None  # 'questions' or 'file_upload'
    display_order: Optional[int] = 0

class ContentReorderRequest(BaseModel):
    """教材排序請求"""
    unit_id: int
    content_subtype: Optional[str] = None
    ordered_ids: List[int]

class HistoryContentAdd(BaseModel):
    generated_content_id: int
    unit_id: int


class ContentDetailResponse(ContentResponse):
    """
    Alias for full response, currently same as ContentResponse.
    Existing endpoints returning ContentResponse will serve as Detail view.
    """
    pass

def _extract_kps_from_content(content: Any) -> set:
    """
    從教材內容中遞迴提取所有相關知識點名稱 (related_kps)
    支援：
    1. 扁平化列表 (list of dicts/questions)
    2. 結構化 dict (含 sections, questions 鍵)
    3. 舊式 wrapper (dict 含 content 鍵)
    """
    kp_names = set()
    
    if isinstance(content, list):
        for item in content:
            kp_names.update(_extract_kps_from_content(item))
            
    elif isinstance(content, dict):
        # 1. 檢查目前層級的 related_kps
        rkps = content.get("related_kps") or content.get("selected_kp_names")
        if isinstance(rkps, list):
            for name in rkps:
                if isinstance(name, str): kp_names.add(name)
        
        # 2. 遞迴檢查子層級
        for key in ["sections", "questions", "content_list", "content"]:
            val = content.get(key)
            if val:
                kp_names.update(_extract_kps_from_content(val))
                
    return kp_names


def _extract_raw_text(content_obj: Any) -> str:
    """
    Extracts a plain text representative of the content (Exam or Material) 
    for fair edit distance comparison.
    """
    if not content_obj:
        return ""
    
    if isinstance(content_obj, str):
        try:
            content_obj = json.loads(content_obj)
        except:
            return content_obj

    text_parts = []
    
    # 0. Include top-level title if present (only valid for dicts)
    if isinstance(content_obj, dict):
        top_title = content_obj.get("title") or content_obj.get("section_title")
        if top_title and isinstance(top_title, str):
            text_parts.append(top_title)

    # 1. Handle Material (Summary/Report)
    if isinstance(content_obj, dict):
        if "sections" in content_obj and isinstance(content_obj["sections"], list):
            for sec in content_obj["sections"]:
                # Handle both 'title' and 'section_title'
                text_parts.append(sec.get("title") or sec.get("section_title") or "")
                
                # Handle both 'content' and 'content_list'
                c_val = sec.get("content") or sec.get("content_list") or ""
                if isinstance(c_val, list):
                    text_parts.extend([str(i) for i in c_val])
                else:
                    text_parts.append(str(c_val))
        elif "content" in content_obj and isinstance(content_obj["content"], str):
             text_parts.append(content_obj["content"])
        
        # 2. Handle Exam (Questions)
        q_list = content_obj.get("questions") or content_obj.get("content")
        if isinstance(q_list, list):
            for q in q_list:
                if not isinstance(q, dict): continue
                text_parts.append(q.get("question_text") or q.get("title") or "")
                options = q.get("options")
                if isinstance(options, list):
                    text_parts.extend([str(opt) for opt in options])
                text_parts.append(str(q.get("correct_answer") or ""))
        
        # Fallback: if it's just a flat dict with no obvious structure, dump it
        if not text_parts:
            text_parts.append(json.dumps(content_obj, ensure_ascii=False))
    elif isinstance(content_obj, list):
        # Case where content is just a list of questions
        for item in content_obj:
            if isinstance(item, dict):
                text_parts.append(item.get("question_text") or item.get("title") or "")
            else:
                text_parts.append(str(item))

    return "\n".join([p for p in text_parts if p]).strip()


def _summarize_content_diff(old_content: Any, new_content: Any) -> Dict[str, Any]:
    """
    Generates a concise summary of changes between two content objects.
    Aims to satisfy the user's request to "not bloat data" by saving only modified parts.
    """
    import difflib
    summary = {"changed_indices": [], "change_details": []}
    
    # helper to check if two values are meaningfully different
    def is_diff(a, b):
        return str(a).strip() != str(b).strip()

    def get_concise_diff(old_text, new_text):
        if not old_text and not new_text: return None
        old_text = str(old_text or "")
        new_text = str(new_text or "")
        if old_text == new_text: return None
        
        # Get line-by-line diff and take only modified lines
        diff = difflib.ndiff(old_text.splitlines(), new_text.splitlines())
        changes = [l for l in diff if l.startswith('+ ') or l.startswith('- ')]
        # Cap to keep history small
        if len(changes) > 10:
            return changes[:5] + ["..."] + changes[-5:]
        return changes

    # Normalize inputs
    if isinstance(old_content, str):
        try: old_content = json.loads(old_content)
        except: pass
    if isinstance(new_content, str):
        try: new_content = json.loads(new_content)
        except: pass

    # 0. Check top-level title (only valid when content is a dict, not a bare list)
    if isinstance(old_content, dict) and isinstance(new_content, dict):
        old_title = old_content.get("title") or old_content.get("section_title")
        new_title = new_content.get("title") or new_content.get("section_title")
        if is_diff(old_title, new_title):
            summary["change_details"].append({
                "field": "title",
                "diff": get_concise_diff(old_title, new_title)
            })

    # 1. Summary/Material structure
    if isinstance(old_content, dict) and "sections" in old_content:
        old_secs = old_content.get("sections") or []
        new_secs = (new_content.get("sections") if isinstance(new_content, dict) else []) or []
        
        for i, (old_s, new_s) in enumerate(zip(old_secs, new_secs)):
            if not isinstance(old_s, dict) or not isinstance(new_s, dict):
                if is_diff(old_s, new_s):
                    summary["changed_indices"].append(i)
                continue
                
            os_title = old_s.get("title") or old_s.get("section_title") or ""
            ns_title = new_s.get("title") or new_s.get("section_title") or ""
            os_c = old_s.get("content") or old_s.get("content_list") or ""
            ns_c = new_s.get("content") or new_s.get("content_list") or ""
            
            # [IMPROVEMENT] If content is a list, join with newlines for cleaner line-by-line diff
            if isinstance(os_c, list): os_c = "\n".join([str(x) for x in os_c])
            if isinstance(ns_c, list): ns_c = "\n".join([str(x) for x in ns_c])

            # Combine for section check
            o_full = f"{os_title}\n{os_c}"
            n_full = f"{ns_title}\n{ns_c}"

            if is_diff(o_full, n_full):
                summary["changed_indices"].append(i)
                summary["change_details"].append({
                    "field": f"section_{i}",
                    "diff": get_concise_diff(o_full, n_full)
                })
        
        if len(new_secs) != len(old_secs):
            summary["change_details"].append({"field": "sections", "action": "count_changed"})

    # 2. Exam/Questions structure
    old_qs = []
    if isinstance(old_content, dict):
        old_qs = old_content.get("questions") or old_content.get("content") or []
    elif isinstance(old_content, list):
        old_qs = old_content
        
    new_qs = []
    if isinstance(new_content, dict):
        new_qs = new_content.get("questions") or new_content.get("content") or []
    elif isinstance(new_content, list) or isinstance(new_content, dict):
        new_qs = (new_content.get("questions") if isinstance(new_content, dict) else new_content) or []

    if isinstance(old_qs, list) and isinstance(new_qs, list):
        for i, (old_q, new_q) in enumerate(zip(old_qs, new_qs)):
            if not isinstance(old_q, dict) or not isinstance(new_q, dict):
                if is_diff(old_q, new_q):
                    summary["changed_indices"].append(i)
                continue
            
            # Combine question parts for a holistic diff of the question card
            o_q_str = f"{old_q.get('question_text', '')}\n{old_q.get('options', [])}\nAns: {old_q.get('correct_answer', '')}"
            n_q_str = f"{new_q.get('question_text', '')}\n{new_q.get('options', [])}\nAns: {new_q.get('correct_answer', '')}"

            if is_diff(o_q_str, n_q_str):
                summary["changed_indices"].append(i)
                summary["change_details"].append({
                    "field": f"question_{i}",
                    "diff": get_concise_diff(o_q_str, n_q_str)
                })
        
        if len(new_qs) != len(old_qs):
            summary["change_details"].append({"field": "questions", "action": "count_changed"})

    return summary


def calculate_edit_ratio(original: str, modified: str) -> Tuple[int, float]:
    """
    Calculate Levenshtein distance and edit ratio between two strings using difflib.
    """
    import difflib
    if not original:
        return (len(modified) if modified else 0), 0.0
    
    # Simple character-based distance (Levenshtein approximation)
    s = difflib.SequenceMatcher(None, original, modified)
    matches = s.get_matching_blocks()
    matched_chars = sum(block.size for block in matches)
    
    # Levenshtein distance: additions + deletions + substitutions
    # SequenceMatcher ratio() is 2*M / (L1+L2). 
    # Our simple distance calc is:
    distance = max(len(original), len(modified)) - matched_chars
    ratio = distance / len(original) if len(original) > 0 else 0.0
    
    return distance, min(ratio, 1.0)

# ==================== Content Creation Endpoints ====================

# ==================== Unified Content Endpoints ====================

def _sync_get_course_contents(course_id: int):
    with engine.connect() as conn:
        # Check course
        check = conn.execute(text("SELECT id FROM courses WHERE id = :cid"), {"cid": course_id}).fetchone()
        if not check:
            return None

        query = text("""
            SELECT cc.id, cc.course_id, cc.unit_id, cc.title,
                   cc.content_type, cc.content_subtype, cc.source_type, cc.source_id,
                   cc.include_in_grade, cc.weight, cc.total_points,
                   cc.is_visible, cc.created_at,
                   at.job_id,
                   cc.assignment_type,
                   cc.display_order
            FROM course_contents cc
            LEFT JOIN generated_contents gc ON (cc.source_id = gc.id AND cc.source_type = 'generated_content')
            LEFT JOIN agent_tasks at ON (gc.source_agent_task_id = at.id)
            WHERE cc.course_id = :course_id
            ORDER BY cc.unit_id NULLS LAST, cc.content_subtype NULLS LAST, cc.display_order ASC, cc.created_at DESC
        """)
        rows = conn.execute(query, {"course_id": course_id}).fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "course_id": row.course_id,
                "unit_id": row.unit_id,
                "title": row.title,
                "content_type": row.content_type,
                "content_subtype": row.content_subtype,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "include_in_grade": row.include_in_grade or False,
                "weight": float(row.weight or 0),
                "total_points": float(row.total_points or 0),
                "is_visible": row.is_visible if row.is_visible is not None else True,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "job_id": row.job_id,
                "assignment_type": row.assignment_type,
                "display_order": row.display_order or 0
            })
        return results

@router.get("/api/courses/{course_id}/contents", response_model=List[ContentListResponse], tags=["Content"])
async def get_course_contents(course_id: int):
    """
    取得課程內容列表（不含content欄位）
    """
    results = await run_in_db_pool(_sync_get_course_contents, course_id)
    
    if results is None:
        raise HTTPException(status_code=404, detail="Course not found")
        
    return [ContentListResponse(**r) for r in results]

@router.post("/api/courses/{course_id}/contents/reorder", tags=["Content"])
async def reorder_course_contents(course_id: int, request: ContentReorderRequest):
    """
    重新排序單元內的教材
    """
    def _sync_reorder():
        with engine.connect() as conn:
            # 遍歷 ordered_ids 並更新 display_order
            for index, content_id in enumerate(request.ordered_ids):
                update_query = text("""
                    UPDATE course_contents
                    SET display_order = :order, updated_at = :now
                    WHERE id = :id AND course_id = :course_id AND unit_id = :unit_id
                """)
                conn.execute(update_query, {
                    "order": index + 1,
                    "id": content_id,
                    "course_id": course_id,
                    "unit_id": request.unit_id,
                    "now": get_now_taipei()
                })
            conn.commit()
            return True

    success = await run_in_db_pool(_sync_reorder)
    if not success:
        raise HTTPException(status_code=500, detail="Reorder failed")
    
    return {"message": "Reorder successful"}

def _sync_create_course_content(course_id: int, item_data: dict, selected_kps_data: list = None):
    with engine.begin() as conn:
        # Check course
        check = conn.execute(text("SELECT id FROM courses WHERE id = :cid"), {"cid": course_id}).fetchone()
        if not check:
            return None, "Course not found"

        # --- Experiment Logging: Handle generated_contents update ---
        levenshtein_distance = None
        edit_ratio = None
        
        if item_data.get("source_type") == "generated_content" and item_data.get("source_id"):
            gc_id = item_data["source_id"]
            
            # Fetch original content to calculate ratio
            orig_query = text("SELECT content FROM generated_contents WHERE id = :id")
            orig_row = conn.execute(orig_query, {"id": gc_id}).fetchone()
            
            if orig_row:
                orig_content_obj = orig_row[0]
                # Extract meaningful text for comparison
                orig_text = _extract_raw_text(orig_content_obj)
                new_content_obj = item_data.get("content") or {}
                new_text = _extract_raw_text(new_content_obj)
                
                levenshtein_distance, edit_ratio = calculate_edit_ratio(orig_text, new_text)
                
                # Update generated_contents with action, snapshot, AND distance metrics
                update_gc_query = text("""
                    UPDATE generated_contents 
                    SET action_type = 'save',
                        edit_duration_seconds = :duration,
                        final_content_snapshot = :snapshot,
                        levenshtein_distance = :l_dist,
                        edit_ratio = :e_ratio,
                        updated_at = :now
                    WHERE id = :id
                """)
                conn.execute(update_gc_query, {
                    "id": gc_id,
                    "duration": item_data.get("edit_duration_seconds"),
                    "snapshot": json.dumps(new_content_obj, ensure_ascii=False),
                    "l_dist": levenshtein_distance,
                    "e_ratio": edit_ratio,
                    "now": get_now_taipei()
                })

                # Prepare initial edit history entry
                initial_history = [{
                    "timestamp": get_now_taipei().isoformat(),
                    "action": "create_from_generation",
                    "levenshtein_distance": levenshtein_distance,
                    "edit_ratio": edit_ratio,
                    "duration_seconds": item_data.get("edit_duration_seconds"),
                    "snapshot_text_v0": orig_text[:500] + "..." if len(orig_text) > 500 else orig_text
                }]
                item_data["edit_history"] = initial_history

        # Prepare content JSON (inject grading if provided)
        content_json = item_data.get("content") or {}
        if item_data.get("question_grading") and isinstance(content_json, dict):
            content_json['question_grading'] = item_data.get("question_grading")
            
        # [FIX] Inject source_ids into content JSON for multi-source tracking if provided
        if item_data.get("source_ids") and isinstance(content_json, dict):
            content_json['source_ids'] = item_data.get("source_ids")
            
        # Get next display_order for this unit and subtype
        order_query = text("""
            SELECT COALESCE(MAX(display_order), 0) + 1
            FROM course_contents
            WHERE unit_id = :uid AND (content_subtype = :csubtype OR (content_subtype IS NULL AND :csubtype IS NULL))
        """)
        next_order = conn.execute(order_query, {
            "uid": item_data.get("unit_id"),
            "csubtype": item_data.get("content_subtype")
        }).scalar() or 1

        insert_query = text("""
            INSERT INTO course_contents (
                course_id, unit_id, title,
                content_type, content_subtype, source_type, source_id, content,
                include_in_grade, weight, total_points, question_grading,
                is_visible, start_time, end_time,
                duration_minutes, allow_review, show_answers_after,
                assignment_type, description,
                author_id,
                display_order,
                edit_history,
                created_at, updated_at
            ) VALUES (
                :cid, :uid, :title,
                :ctype, :csubtype, :stype, :sid, :content,
                :ingrade, :weight, :points, :qgrading,
                :vis, :start_time, :end_time,
                :duration_minutes, :allow_review, :show_answers_after,
                :assignment_type, :description,
                :author_id,
                :display_order,
                :e_history,
                :now, :now
            )
            RETURNING id, created_at
        """)
        
        # Prepare question_grading JSON
        q_grading_json = None
        if item_data.get("question_grading"):
            q_grading_json = json.dumps(item_data["question_grading"], ensure_ascii=False)

        result = conn.execute(insert_query, {
            "cid": course_id,
            "uid": item_data.get("unit_id"),
            "title": item_data["title"],
            "ctype": item_data["content_type"],
            "csubtype": item_data.get("content_subtype"),
            "stype": item_data["source_type"],
            "sid": item_data["source_id"],
            "content": json.dumps(content_json, ensure_ascii=False),
            "ingrade": item_data.get("include_in_grade", False),
            "weight": item_data.get("weight", 0.0),
            "points": item_data.get("total_points", 100.0),
            "qgrading": q_grading_json,
            "vis": item_data.get("is_visible", True),
            "now": get_now_taipei(),
            "start_time": item_data.get("start_time"),
            "end_time": item_data.get("end_time"),
            "duration_minutes": item_data.get("duration_minutes"),
            "allow_review": item_data.get("allow_review", True),
            "show_answers_after": item_data.get("show_answers_after"),
            # assignment_type only makes sense for exam; material gets NULL
            "assignment_type": item_data.get("assignment_type") if item_data.get("assignment_type") is not None
                               else ("questions" if item_data.get("content_type") == "exam" else None),
            "description": item_data.get("description"),
            "author_id": item_data.get("author_id"),
            "display_order": next_order,
            "e_history": json.dumps(item_data.get("edit_history", []), ensure_ascii=False)
        })
        
        row = result.fetchone()
        content_id = row[0]
        created_at = row[1]
        
        # ✅ KP Promotion and Linking Logic
        # Prioritize selected_kps (structured), fallback to selected_kp_names
        kps_to_process = []
        if selected_kps_data:
            kps_to_process = selected_kps_data
        elif item_data.get("selected_kp_names"):
             kps_to_process = [{"name": name, "level": "sub_technique"} for name in item_data["selected_kp_names"]]

        # [NEW] Also extract from content itself recursively
        extracted_kp_names = _extract_kps_from_content(content_json)
        
        if (kps_to_process or extracted_kp_names) and item_data.get("unit_id"):
            logger.info(f"🔄 Processing KP Promotion for content {content_id}")
            
            # Fetch ALL existing KPs for this unit to perform fuzzy matching
            all_unit_kps_query = text("SELECT id, name FROM knowledge_points WHERE unit_id = :uid")
            all_unit_kps = conn.execute(all_unit_kps_query, {"uid": item_data["unit_id"]}).fetchall()
            all_kp_map = {r.name: r.id for r in all_unit_kps}
            existing_names = list(all_kp_map.keys())

            unique_kps = {}
            for kp in kps_to_process:
                name = kp["name"]
                if name not in unique_kps:
                    unique_kps[name] = kp
            
            is_generated = item_data.get("source_type") == "generated_content"
            
            import difflib
            for name in extracted_kp_names:
                # 1. Exact match check
                if name in all_kp_map:
                    if name not in unique_kps:
                        unique_kps[name] = {"name": name, "level": "sub_technique"}
                    continue
                
                # 2. Fuzzy match to existing unit KPs (prevent drift)
                matches = difflib.get_close_matches(name, existing_names, n=1, cutoff=0.8)
                if matches:
                    matched_name = matches[0]
                    logger.info(f"🔮 Fuzzy matched hallucinated KP '{name}' -> '{matched_name}'")
                    if matched_name not in unique_kps:
                        unique_kps[matched_name] = {"name": matched_name, "level": "sub_technique"}
                    continue
                
                # 3. If no match and it's generated, IGNORE it. Do not create "ghost" KPs.
                if is_generated:
                    logger.warning(f"🚫 Ignoring unknown KP '{name}' from generated content to prevent ghost KPs.")
                    continue
                    
                # 4. For uploaded/manual content, allowed to create new KPs
                if name not in unique_kps:
                    unique_kps[name] = {"name": name, "level": "sub_technique"}

            kp_names = list(unique_kps.keys())
            
            # Final mapping of names to IDs
            existing_kp_map = {name: all_kp_map[name] for name in kp_names if name in all_kp_map}
            
            # Promote (Insert) non-existing KPs (only for non-generated content at this point)
            new_kps = [kp for kp in unique_kps.values() if kp["name"] not in existing_kp_map]
            
            # Level to Display Order Mapping
            LEVEL_TO_ORDER = {
                'big_idea': 1,
                'core_concept': 2,
                'sub_technique': 3,
                'unknown': 4
            }
            
            for kp in new_kps:
                level = kp.get("level", "sub_technique")
                display_order = LEVEL_TO_ORDER.get(level, 3) 
                
                insert_kp_query = text("""
                    INSERT INTO knowledge_points (unit_id, course_id, name, display_order) 
                    VALUES (:uid, :cid, :name, :order) 
                    RETURNING id
                """)
                res = conn.execute(insert_kp_query, {
                    "uid": item_data["unit_id"], 
                    "cid": course_id, 
                    "name": kp["name"],
                    "order": display_order
                })
                new_id = res.fetchone()[0]
                existing_kp_map[kp["name"]] = new_id
                logger.info(f"✨ Promoted new KP: '{kp['name']}' (ID: {new_id}, Order: {display_order})")
                
            # 3. Link Content to KPs
            if existing_kp_map:
                link_values = []
                for name in kp_names:
                    kp_id = existing_kp_map.get(name)
                    if kp_id:
                        link_values.append({"ccid": content_id, "kpid": kp_id})
                
                if link_values:
                    conn.execute(text("""
                        INSERT INTO course_content_knowledge_points (course_content_id, knowledge_point_id) 
                        VALUES (:ccid, :kpid)
                        ON CONFLICT DO NOTHING
                    """), link_values)

        conn.commit()
        
        logger.info(f"✅ Successfully created unified content: ID={content_id}, Type={item_data['content_type']}, Title='{item_data['title']}'")
        
        return {
            "id": content_id,
            "created_at": created_at.isoformat()
        }, None

def _sync_get_job_id_from_generated_content(gc_id: int):
    """
    Helper to look up the original orchestration job ID and iteration number 
    from a generated content record. Used for attribution.
    """
    with engine.connect() as conn:
        query = text("""
            SELECT at.job_id, at.iteration_number
            FROM generated_contents gc
            JOIN agent_tasks at ON gc.source_agent_task_id = at.id
            WHERE gc.id = :gc_id
        """)
        res = conn.execute(query, {"gc_id": gc_id}).fetchone()
        if res:
            return {"job_id": res[0], "iteration_count": res[1]}
        return {"job_id": None, "iteration_count": 1}

@router.post("/api/courses/{course_id}/contents", response_model=ContentResponse, tags=["Content"])
async def create_course_content(
    course_id: int, 
    item: ContentCreate,
    background_tasks: BackgroundTasks
):
    """
    建立課程內容 (Unified)
    包含 KP Promotion 和 Linking 邏輯
    """
    item_dict = item.dict()
    # Pydantic dict() renders models as dicts, so selected_kps is list of dicts
    selected_kps_data = item_dict.get("selected_kps")
    
    # Pass item_dict directly, authorize via payload if needed or just accept it for now
    result_data, error = await run_in_db_pool(_sync_create_course_content, course_id, item_dict, selected_kps_data)
    
    if error == "Course not found":
        raise HTTPException(status_code=404, detail="Course not found")
    elif error:
        raise HTTPException(status_code=500, detail=error)
    
    content_id = result_data["id"]
    created_at_str = result_data["created_at"]

    # [INGESTION TRIGGER]
    job_id = None
    if item.source_type == 'generated_content':
            # Attempt to fetch job info for background task logging
            job_info = await run_in_db_pool(_sync_get_job_id_from_generated_content, item.source_id)
            job_id = job_info.get("job_id")
            iteration_count = job_info.get("iteration_count", 1)
            
            from backend.app.agents.teacher_agent.ingestion import ingest_course_content
            # Pass job_id and iteration_count
            background_tasks.add_task(
                ingest_course_content, 
                content_id, 
                job_id=job_id, 
                iteration_count=iteration_count
            )

    return ContentResponse(
        id=content_id,
        course_id=course_id,
        unit_id=item.unit_id,
        title=item.title,
        content_type=item.content_type,
        content_subtype=item.content_subtype,
        source_type=item.source_type,
        source_id=item.source_id,
        content=item.content,
        include_in_grade=item.include_in_grade,
        weight=item.weight,
        total_points=item.total_points,
        question_grading=item.question_grading,
        
        is_visible=item.is_visible,
        start_time=item.start_time,
        end_time=item.end_time,
        duration_minutes=item.duration_minutes,
        allow_review=item.allow_review,
        show_answers_after=item.show_answers_after,
        
        created_at=created_at_str,
        job_id=job_id
    )

def _sync_get_course_content(course_id: int, content_id: int):
    with engine.connect() as conn:
        # Join to get job_id
        query = text("""
            SELECT cc.id, cc.course_id, cc.unit_id, cc.title,
                   cc.content_type, cc.content_subtype, cc.source_type, cc.source_id, cc.content,
                   cc.include_in_grade, cc.weight, cc.total_points,
                   cc.is_visible, cc.start_time, cc.end_time,
                   cc.duration_minutes, cc.allow_review, cc.show_answers_after,
                   cc.assignment_type, cc.description,
                   cc.created_at,
                   at.job_id
            FROM course_contents cc
            LEFT JOIN generated_contents gc ON (cc.source_id = gc.id AND cc.source_type = 'generated_content')
            LEFT JOIN agent_tasks at ON (gc.source_agent_task_id = at.id)
            WHERE cc.id = :id AND cc.course_id = :cid
        """)
        row = conn.execute(query, {"id": content_id, "cid": course_id}).fetchone()
        if not row:
            return None
        return dict(row._mapping)

# ==================== Experiment Logging Endpoints ====================

class TeacherActionLogRequest(BaseModel):
    generated_content_id: int
    action_type: str  # 'discard', 'regenerate'
    edit_duration_seconds: int
    content_snapshot: Any

@router.post("/api/teacher/logs/action", tags=["Experiment Logging"])
async def log_teacher_action(payload: TeacherActionLogRequest):
    """
    紀錄教師對於生成內容的決策（取消或重新設定）
    含最後內容快照、編輯時長、以及相較於原始生成內容的修改幅度 (Academic Logging)
    """
    def _sync_log():
        with engine.begin() as conn:
            # 1. Fetch original content to calculate distance metrics
            # We compare the original content (at the time of generation) with the final snapshot before action
            orig_row = conn.execute(
                text("SELECT content FROM generated_contents WHERE id = :id"),
                {"id": payload.generated_content_id}
            ).fetchone()
            
            l_dist = 0
            e_ratio = 0.0
            
            if orig_row and orig_row[0]:
                orig_content = orig_row[0]
                # Extract text for comparison
                orig_text = _extract_raw_text(orig_content)
                new_text = _extract_raw_text(payload.content_snapshot)
                
                # Calculate metrics
                l_dist, e_ratio = calculate_edit_ratio(orig_text, new_text)

            # 2. Update generated_contents with action, snapshot, AND distance metrics
            query = text("""
                UPDATE generated_contents 
                SET action_type = :action,
                    edit_duration_seconds = :duration,
                    final_content_snapshot = :snapshot,
                    levenshtein_distance = :l_dist,
                    edit_ratio = :e_ratio,
                    updated_at = :now
                WHERE id = :id
            """)
            conn.execute(query, {
                "id": payload.generated_content_id,
                "action": payload.action_type,
                "duration": payload.edit_duration_seconds,
                "snapshot": json.dumps(payload.content_snapshot, ensure_ascii=False) if not isinstance(payload.content_snapshot, str) else payload.content_snapshot,
                "l_dist": l_dist,
                "e_ratio": e_ratio,
                "now": get_now_taipei()
            })
            return True

    await run_in_db_pool(_sync_log)
    return {"message": "Action logged successfully"}


@router.post("/api/courses/{course_id}/contents/{content_id}/view", tags=["Experiment Logging"])
async def increment_content_view(course_id: int, content_id: int):
    """
    增加教師對於教材的檢視次數
    """
    def _sync_inc():
        with engine.begin() as conn:
            query = text("""
                UPDATE course_contents 
                SET view_count = view_count + 1
                WHERE id = :id AND course_id = :cid
            """)
            conn.execute(query, {"id": content_id, "cid": course_id})
            return True

    await run_in_db_pool(_sync_inc)
    return {"message": "View count incremented"}

class SourcePreviewLogRequest(BaseModel):
    # One of these must be set: applies to the current editing context
    generated_content_id: Optional[int] = None
    course_content_id: Optional[int] = None
    # The chunk/source that was viewed
    source_id: Optional[int] = None
    chunk_id: Optional[Union[str, int]] = None  # May be prefixed string e.g. 'doc_123'
    # Context: which content item triggered the reference click
    # For exam content: question_id (question display number or DB id)
    # For summary content: section_id (0-based section index)
    section_id: Optional[Union[str, int]] = None
    question_id: Optional[Union[str, int]] = None
    # Timing
    view_start: str  # ISO timestamp when drawer opened
    view_seconds: int  # seconds the drawer was open

@router.post("/api/teacher/logs/source_preview", tags=["Experiment Logging"])
async def log_source_preview(payload: SourcePreviewLogRequest):
    """
    Log a single instance of a teacher opening the RAG reference panel.
    Called immediately when the Reference Drawer is closed.
    Appends to source_preview_logs JSONB array in generated_contents or course_contents.
    """
    if not payload.generated_content_id and not payload.course_content_id:
        return {"message": "No target content id provided, skipping log"}

    log_entry = {
        "source_id": payload.source_id,
        "chunk_id": str(payload.chunk_id) if payload.chunk_id is not None else None,
        "view_start": payload.view_start,
        "view_seconds": payload.view_seconds
    }
    if payload.section_id is not None:
        log_entry["section_id"] = payload.section_id
    if payload.question_id is not None:
        log_entry["question_id"] = payload.question_id


    def _sync_log():
        try:
            entry_json = json.dumps(log_entry, ensure_ascii=False)
            with engine.begin() as conn:
                if payload.generated_content_id:
                    conn.execute(
                        text("""
                            UPDATE generated_contents
                            SET source_preview_logs = COALESCE(source_preview_logs, '[]'::jsonb)
                                                      || cast(:entry AS jsonb)
                            WHERE id = :id
                        """),
                        {
                            "id": payload.generated_content_id,
                            "entry": f"[{entry_json}]"
                        }
                    )
                if payload.course_content_id:
                    conn.execute(
                        text("""
                            UPDATE course_contents
                            SET source_preview_logs = COALESCE(source_preview_logs, '[]'::jsonb)
                                                      || cast(:entry AS jsonb)
                            WHERE id = :id
                        """),
                        {
                            "id": payload.course_content_id,
                            "entry": f"[{entry_json}]"
                        }
                    )
            return True
        except Exception as e:
            logger.error(f"[source_preview] DB error: {e}", exc_info=True)
            raise

    await run_in_db_pool(_sync_log)
    return {"message": "Source preview logged"}



@router.post("/api/courses/{course_id}/contents/add_from_history", tags=["Content"])
async def add_content_from_history(
    course_id: int,
    payload: HistoryContentAdd
):
    """
    Directly adds a generated content from history to a unit.
    If the content currently has no unit_id (was removed), it just updates the unit_id.
    If it is already in a unit, it duplicates the row for the new unit.
    """
    def _sync_add():
        with engine.begin() as conn:
            
            # Find the existing course_contents row
            query = text("""
                SELECT * FROM course_contents 
                WHERE course_id = :cid AND source_type = 'generated_content' AND source_id = :sid
                ORDER BY id ASC LIMIT 1
            """)
            row = conn.execute(query, {"cid": course_id, "sid": payload.generated_content_id}).fetchone()
            
            if not row:
                return "not_found"
                
            # If the unit_id is None, we can just attach it directly
            if row.unit_id is None:
                update_query = text("""
                    UPDATE course_contents SET unit_id = :uid WHERE id = :id
                """)
                conn.execute(update_query, {"uid": payload.unit_id, "id": row.id})
                return {"id": row.id}
            else:
                # Duplicate the row
                insert_query = text("""
                    INSERT INTO course_contents (
                        course_id, unit_id, title, content_type, content_subtype,
                        source_type, source_id, content, include_in_grade, weight,
                        total_points, is_visible, start_time, end_time,
                        duration_minutes, allow_review, show_answers_after,
                        assignment_type, description, order_index
                    ) VALUES (
                        :course_id, :unit_id, :title, :content_type, :content_subtype,
                        :source_type, :source_id, :content, :include_in_grade, :weight,
                        :total_points, :is_visible, :start_time, :end_time,
                        :duration_minutes, :allow_review, :show_answers_after,
                        :assignment_type, :description, :order_index
                    ) RETURNING id
                """)
                new_id = conn.execute(insert_query, {
                    "course_id": course_id,
                    "unit_id": payload.unit_id,
                    "title": row.title,
                    "content_type": row.content_type,
                    "content_subtype": row.content_subtype,
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "content": json.dumps(row.content, ensure_ascii=False) if not isinstance(row.content, dict) else row.content,
                    "include_in_grade": row.include_in_grade,
                    "weight": row.weight,
                    "total_points": row.total_points,
                    "is_visible": row.is_visible,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "duration_minutes": row.duration_minutes,
                    "allow_review": row.allow_review,
                    "show_answers_after": row.show_answers_after,
                    "assignment_type": row.assignment_type,
                    "description": row.description,
                    "order_index": 999
                }).scalar()
                return {"id": new_id}

    result = await run_in_db_pool(_sync_add)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Historical content not found in this course")
        
    return {"message": "Content successfully added", "content_id": result["id"]}

@router.get("/api/courses/{course_id}/contents/{content_id}", response_model=ContentDetailResponse, tags=["Content"])
async def get_course_content(course_id: int, content_id: int):
    """
    取得單一內容詳情 (Unified, 含 content)
    """
    result = await run_in_db_pool(_sync_get_course_content, course_id, content_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Content not found")
    
    content_data = result["content"] if result["content"] else {}
    q_grading = content_data.get('question_grading') if isinstance(content_data, dict) else None
    
    return ContentResponse(
        id=result["id"],
        course_id=result["course_id"],
        unit_id=result["unit_id"],
        title=result["title"],
        content_type=result["content_type"],
        content_subtype=result["content_subtype"],
        source_type=result["source_type"],
        source_id=result["source_id"],
        source_ids=result.get("source_ids"),
        content=result["content"],
        include_in_grade=result["include_in_grade"],
        weight=result["weight"],
        total_points=result["total_points"],
        question_grading=q_grading,
        
        is_visible=result["is_visible"],
        start_time=result["start_time"],
        end_time=result["end_time"],
        duration_minutes=result["duration_minutes"],
        allow_review=result["allow_review"],
        show_answers_after=result["show_answers_after"],
        assignment_type=result.get("assignment_type"),
        description=result.get("description"),
        
        created_at=(result["created_at"].isoformat() if result["created_at"].tzinfo else result["created_at"].isoformat() + "Z") if result.get("created_at") else None,
        job_id=result.get("job_id")
    )

def _sync_update_course_content(course_id: int, content_id: int, item_data: dict, content_json: dict = None):
    with engine.connect() as conn:
        # Check existence and type
        existing = conn.execute(
            text("SELECT id, title, content, source_type FROM course_contents WHERE id = :id AND course_id = :cid"),
            {"id": content_id, "cid": course_id}
        ).fetchone()

        
        if not existing:
            return None, "Content not found"
            
        current_source_type = existing.source_type
            
        # Build update query dynamically
        updates = []
        params = {"id": content_id, "cid": course_id}
        
        if "title" in item_data:
            updates.append("title = :title")
            params['title'] = item_data["title"]

        if "unit_id" in item_data:
            updates.append("unit_id = :uid")
            params['uid'] = item_data["unit_id"]
        
        if "content" in item_data:
            updates.append("content = :content")
            params['content'] = json.dumps(item_data["content"], ensure_ascii=False)

            if "question_grading" in item_data:
                updates.append("question_grading = :qgrading")
                params['qgrading'] = json.dumps(item_data["question_grading"], ensure_ascii=False) if item_data["question_grading"] else None
            
        if "content_type" in item_data:
            updates.append("content_type = :ctype")
            params['ctype'] = item_data["content_type"]
            
        if "content_subtype" in item_data:
            updates.append("content_subtype = :csubtype")
            params['csubtype'] = item_data["content_subtype"]
            
        if "include_in_grade" in item_data:
            updates.append("include_in_grade = :ingrade")
            params['ingrade'] = item_data["include_in_grade"]
            
        if "weight" in item_data:
            updates.append("weight = :weight")
            params['weight'] = item_data["weight"]

        if "total_points" in item_data:
            updates.append("total_points = :points")
            params['points'] = item_data["total_points"]

        if "is_visible" in item_data:
             updates.append("is_visible = :vis")
             params['vis'] = item_data["is_visible"]
        
        # Publishing settings
        if "start_time" in item_data:
            updates.append("start_time = :start_time")
            params['start_time'] = item_data["start_time"]
        if "end_time" in item_data:
            updates.append("end_time = :end_time")
            params['end_time'] = item_data["end_time"]
        if "duration_minutes" in item_data:
            updates.append("duration_minutes = :duration_minutes")
            params['duration_minutes'] = item_data["duration_minutes"]
        if "allow_review" in item_data:
            updates.append("allow_review = :allow_review")
            params['allow_review'] = item_data["allow_review"]
        if "show_answers_after" in item_data:
            updates.append("show_answers_after = :show_answers_after")
            params['show_answers_after'] = item_data["show_answers_after"]
        
        # File upload assignment fields
        if "assignment_type" in item_data:
            updates.append("assignment_type = :assignment_type")
            params['assignment_type'] = item_data["assignment_type"]
        if "description" in item_data:
            updates.append("description = :description")
            params['description'] = item_data["description"]
            
        if "source_ids" in item_data and isinstance(item_data["source_ids"], list):
            # Inject into content JSONB
            params_content = params.get('content')
            if params_content:
                try:
                    c_json = json.loads(params_content)
                    c_json['source_ids'] = item_data["source_ids"]
                    params['content'] = json.dumps(c_json, ensure_ascii=False)
                except:
                    pass
        # [EXPERIMENT LOGGING] Record edit_history whenever title or content changes.
        # Previously only fired on content changes; title-only saves were invisible.
        has_content_change = "content" in item_data
        has_title_change = "title" in item_data and item_data["title"] != (existing.title or "")

        if has_content_change or has_title_change:
            # Calculate combined diff for title + content
            old_title_val = existing.title or ""
            new_title_val = item_data.get("title", old_title_val)
            
            old_text_raw = _extract_raw_text(existing.content)
            new_text_raw = _extract_raw_text(item_data.get("content", existing.content))
            
            # Combine title and content for distance calculation
            orig_combined = f"{old_title_val}\n{old_text_raw}"
            new_combined = f"{new_title_val}\n{new_text_raw}"
            
            dist, ratio = calculate_edit_ratio(orig_combined, new_combined)
            logger.info(f"Tracking Edit (Combined): Content ID {content_id}. Dist: {dist}, Ratio: {ratio}")
            
            if has_content_change:
                diff_summary = _summarize_content_diff(existing.content, item_data["content"])

            if has_title_change:
                old_title_val = existing.title or ""
                new_title_val = item_data["title"]
                if "change_details" not in diff_summary:
                    diff_summary["change_details"] = []
                diff_summary["change_details"].insert(0, {
                    "field": "course_title",
                    "old": old_title_val,
                    "new": new_title_val
                })
                logger.info(f"Tracking Title Change: Content ID {content_id}. '{old_title_val}' -> '{new_title_val}'")

            params['new_dist'] = dist
            params['new_ratio'] = ratio

            # Update revision count
            updates.append("revision_count = revision_count + 1")

            if "edit_duration_seconds" in item_data:
                updates.append("total_edit_duration_seconds = total_edit_duration_seconds + :duration")
                params['duration'] = item_data["edit_duration_seconds"]

            updates.append("""
                edit_history = COALESCE(edit_history, '[]'::jsonb) || jsonb_build_array(
                    jsonb_build_object(
                        'timestamp', :now,
                        'action', 'edit',
                        'distance', :new_dist,
                        'ratio', :new_ratio,
                        'duration', :duration,
                        'diff_summary', :diff_summary
                    )
                )
            """)
            params['diff_summary'] = json.dumps(diff_summary, ensure_ascii=False)
            if 'duration' not in params: params['duration'] = 0

        updates.append("updated_at = :now")
        
        if not updates:
            return None, "No fields to update"
            
        query = text(f"UPDATE course_contents SET {', '.join(updates)} WHERE id = :id AND course_id = :cid RETURNING *")
        
        params['now'] = get_now_taipei()
        result = conn.execute(query, params)
        row = result.fetchone()

        # [NEW] Sync Knowledge Points during update
        if row and "content" in item_data:
            content_json = item_data["content"]
            if isinstance(content_json, (dict, list)):
                # Similar logic to _sync_create_course_content but for update
                # Clear old links and re-add based on current content
                conn.execute(text("DELETE FROM course_content_knowledge_points WHERE course_content_id = :id"), {"id": content_id})
                
                kp_names = _extract_kps_from_content(content_json)

                
                if kp_names:
                    # Resolve IDs (Promote if new)
                    query_existing = text("SELECT id, name FROM knowledge_points WHERE course_id = :cid")
                    existing_kps = conn.execute(query_existing, {"cid": course_id}).fetchall()
                    existing_kp_map = {r.name: r.id for r in existing_kps}
                    
                    for name in kp_names:
                        if name not in existing_kp_map:
                            # Promote extracted KP to stored KP table
                            insert_kp = text("""
                                INSERT INTO knowledge_points (unit_id, course_id, name, display_order)
                                VALUES (:uid, :cid, :name, 4)
                                RETURNING id
                            """)
                            res = conn.execute(insert_kp, {
                                "uid": row.unit_id,
                                "cid": course_id,
                                "name": name
                            })
                            existing_kp_map[name] = res.fetchone()[0]
                    
                    # Insert links
                    link_values = [{"ccid": content_id, "kpid": existing_kp_map[name]} for name in kp_names if name in existing_kp_map]
                    if link_values:
                        conn.execute(text("""
                            INSERT INTO course_content_knowledge_points (course_content_id, knowledge_point_id)
                            VALUES (:ccid, :kpid)
                            ON CONFLICT DO NOTHING
                        """), link_values)

        conn.commit()
        if not row:
            return None, "Update failed"
        
        return {
            "row": {
                 "id": row.id,
                 "course_id": row.course_id,
                 "unit_id": row.unit_id,
                 "title": row.title,
                 "content_type": row.content_type,
                 "content_subtype": row.content_subtype,
                 "source_type": row.source_type,
                 "source_id": row.source_id,
                 "source_ids": row.content.get("source_ids") if isinstance(row.content, dict) else None,
                 "content": row.content,

                 "content_type": row.content_type,
                 "content_subtype": row.content_subtype,
                 "source_type": row.source_type,
                 "source_id": row.source_id,
                 "content": row.content,
                 "include_in_grade": row.include_in_grade,
                 "weight": row.weight,
                 "total_points": row.total_points,
                 "question_grading": row.question_grading,
                 
                 "is_visible": row.is_visible,
                 
                 "start_time": row.start_time,
                 "end_time": row.end_time,
                 "duration_minutes": row.duration_minutes,
                 "allow_review": row.allow_review,
                 "show_answers_after": row.show_answers_after,

                 "created_at": row.created_at
            },
            "source_type": current_source_type
        }, None

@router.put("/api/courses/{course_id}/contents/{content_id}", response_model=ContentResponse, tags=["Content"])
async def update_course_content(
    course_id: int, 
    content_id: int, 
    item: ContentUpdate,
    background_tasks: BackgroundTasks
):
    """
    更新課程內容 (Unified)
    """
    from backend.app.agents.teacher_agent.ingestion import ingest_course_content
    
    item_dict = item.dict(exclude_unset=True)
    result, error = await run_in_db_pool(_sync_update_course_content, course_id, content_id, item_dict)
    
    if error == "Content not found":
        raise HTTPException(status_code=404, detail="Content not found")
    elif error == "No fields to update":
        raise HTTPException(status_code=400, detail="No fields to update")
    elif error:
        raise HTTPException(status_code=500, detail=error)
    
    row_data = result["row"]
    current_source_type = result["source_type"]
    
    # [INGESTION TRIGGER]
    if current_source_type == 'generated_content':
         # Fetch job info for background task logging
         job_info = await run_in_db_pool(_sync_get_job_id_from_generated_content, row_data["source_id"])
         job_id = job_info.get("job_id")
         iteration_count = job_info.get("iteration_count", 1)
         
         from backend.app.agents.teacher_agent.ingestion import ingest_course_content
         # Pass job_id and iteration_count
         background_tasks.add_task(
             ingest_course_content, 
             content_id, 
             job_id=job_id, 
             iteration_count=iteration_count
         )
    
    content_data = row_data["content"] if row_data["content"] else {}
    q_grading = content_data.get('question_grading') if isinstance(content_data, dict) else None
    
    return ContentResponse(
        id=row_data["id"],
        course_id=row_data["course_id"],
        unit_id=row_data["unit_id"],
        title=row_data["title"],
        content_type=row_data["content_type"],
        content_subtype=row_data["content_subtype"],
        source_type=row_data["source_type"],
        source_id=row_data["source_id"],
        content=row_data["content"],
        include_in_grade=row_data["include_in_grade"] or False,
        weight=float(row_data["weight"] or 0),
        total_points=float(row_data["total_points"] or 0),
        question_grading=row_data.get("question_grading"),
        
        is_visible=row_data["is_visible"] if row_data["is_visible"] is not None else True,
        start_time=row_data["start_time"],
        end_time=row_data["end_time"],
        duration_minutes=row_data["duration_minutes"],
        allow_review=row_data["allow_review"],
        show_answers_after=row_data["show_answers_after"],
        
        created_at=row_data["created_at"].isoformat()
    )


def _sync_remove_content_from_unit(course_id: int, content_id: int):
    with engine.connect() as conn:
        # Check existence
        existing = conn.execute(
            text("SELECT id, title, unit_id FROM course_contents WHERE id = :id AND course_id = :cid"),
            {"id": content_id, "cid": course_id}
        ).fetchone()
        
        if not existing:
            return None
        
        # Set unit_id to NULL
        update_query = text("""
            UPDATE course_contents 
            SET unit_id = NULL, updated_at = :now
            WHERE id = :id AND course_id = :cid
        """)
        
        conn.execute(update_query, {"id": content_id, "cid": course_id, "now": get_now_taipei()})
        conn.commit()
        return {"id": existing.id, "title": existing.title, "unit_id": existing.unit_id}

@router.patch("/api/courses/{course_id}/contents/{content_id}/remove", tags=["Content"])
async def remove_content_from_unit(course_id: int, content_id: int):
    """
    從單元中移除內容 (軟刪除) - 將 unit_id 設為 NULL
    內容仍保留在歷史紀錄中，可重新加入到其他單元
    """
    result = await run_in_db_pool(_sync_remove_content_from_unit, course_id, content_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Content not found")
        
    logger.info(f"✅ Removed content {content_id} ('{result['title']}') from unit {result['unit_id']}")
    return {"message": "已從章節移除", "content_id": content_id, "previous_unit_id": result["unit_id"]}

def _sync_delete_course_content(course_id: int, content_id: int):
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM course_contents WHERE id = :id AND course_id = :cid"),
            {"id": content_id, "cid": course_id}
        )
        conn.commit()
        return result.rowcount > 0

@router.delete("/api/courses/{course_id}/contents/{content_id}", tags=["Content"])
async def delete_course_content(course_id: int, content_id: int):
    """
    刪除課程內容
    """
    success = await run_in_db_pool(_sync_delete_course_content, course_id, content_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Content not found")
            
    return {"message": "Content deleted"}
# ==================== Knowledge Points ====================

def _sync_get_course_knowledge_points(course_id: int, unit_id: Optional[int] = None):
    with engine.connect() as conn:
        # Load stored KPs
        query_stored = text("""
            SELECT id, name, unit_id, source_type, source_name
            FROM knowledge_points
            WHERE course_id = :course_id
            ORDER BY unit_id NULLS LAST, display_order ASC
        """)
        stored_rows = conn.execute(query_stored, {"course_id": course_id}).fetchall()
        
        # Load extracted KPs (Filtered by Unit if provided)
        # We join with knowledge_points to get global IDs if they exist
        query_extracted = text(f"""
            SELECT dkp.knowledge_point_name, MAX(kp.id) as global_id, MAX(uc.file_name) as source_name
            FROM document_knowledge_points dkp
            JOIN uploaded_contents uc ON dkp.unique_content_id = uc.unique_content_id
            LEFT JOIN knowledge_points kp ON kp.name = dkp.knowledge_point_name AND kp.course_id = :course_id
            WHERE uc.course_id = :course_id AND dkp.is_active = true
            {"AND uc.unit_id = :unit_id" if unit_id else ""}
            GROUP BY dkp.knowledge_point_name
            
            UNION
            
            SELECT dkp.knowledge_point_name, MAX(kp.id) as global_id, MAX(cc.title) as source_name
            FROM document_knowledge_points dkp
            JOIN course_contents cc ON dkp.unique_content_id = cc.source_id
            LEFT JOIN knowledge_points kp ON kp.name = dkp.knowledge_point_name AND kp.course_id = :course_id
            WHERE cc.course_id = :course_id AND cc.source_type = 'generated_content' AND dkp.is_active = true
            {"AND cc.unit_id = :unit_id" if unit_id else ""}
            GROUP BY dkp.knowledge_point_name
        """)
        
        extracted_rows = conn.execute(query_extracted, {"course_id": course_id, "unit_id": unit_id}).fetchall()
        
        # Categorize
        kps = []
        seen_names = set()
        
        # Category order: unit > extracted > course
        
        # 1. Unit KPs
        # 1. Stored KPs (Manual/Promoted - Highest Priority)
        for row in stored_rows:
            if unit_id is None or row.unit_id == unit_id:
                kps.append({
                    "id": row.id, 
                    "name": row.name, 
                    "category": "unit" if row.unit_id else "course",
                    "source_type": row.source_type,
                    "source_name": row.source_name
                })
                seen_names.add(row.name)
        
        # 2. Extracted KPs (Renamed per user request)
        for row in extracted_rows:
            name = row[0]
            existing_id = row[1]
            source_name = row[2] # file_name or cc.title
            if name not in seen_names:
                kps.append({
                    "id": existing_id, 
                    "name": name, 
                    "category": "extracted",
                    "source_name": source_name
                })
                seen_names.add(name)
                
        # 3. Course KPs (pinned but no unit)
        # 3. Rest of Stored KPs (If any were missed)
        for row in stored_rows:
            if row.name not in seen_names:
                kps.append({
                    "id": row.id, 
                    "name": row.name, 
                    "category": "unit" if row.unit_id else "course",
                    "source_type": row.source_type,
                    "source_name": row.source_name
                })
                seen_names.add(row.name)
        
        return kps

@router.get("/api/courses/{course_id}/knowledge-points", tags=["Courses"])
async def get_course_knowledge_points(
    course_id: int, 
    unit_id: Optional[int] = Query(None, description="篩選單元知識點")
):
    """
    取得課程的所有知識點（支援分組：單元、提取、課程）
    """
    kps_data = await run_in_db_pool(_sync_get_course_knowledge_points, course_id, unit_id)
    return kps_data

def _sync_get_content_knowledge_points(course_id: int, unique_content_ids: List[int]):
    with engine.connect() as conn:
        # 策略：從 document_knowledge_points 中獲取指定教材的 KP
        # 同時試圖與全域 knowledge_points 對齊名字，若有的話回傳全域 ID
        query = text("""
            SELECT 
                dkp.id as doc_kp_id,
                dkp.knowledge_point_name as name,
                kp.id as global_id,
                dkp.mermaid_node_id,
                COALESCE(uc.file_name, cc.title) as source_name
            FROM document_knowledge_points dkp
            LEFT JOIN uploaded_contents uc ON dkp.unique_content_id = uc.unique_content_id
            LEFT JOIN course_contents cc ON (dkp.unique_content_id = cc.source_id AND cc.source_type = 'generated_content')
            LEFT JOIN knowledge_points kp ON kp.name = dkp.knowledge_point_name AND kp.course_id = :course_id
            WHERE dkp.unique_content_id IN :unique_content_ids
            AND dkp.is_active = true
            ORDER BY dkp.id ASC
        """)
        
        result = conn.execute(query, {
            "course_id": course_id,
            "unique_content_ids": tuple(unique_content_ids)
        })
        
        kps = []
        seen_names = set()
        for row in result:
            name = row[1]
            if name in seen_names:
                continue
            seen_names.add(name)
            
            kps.append({
                "id": str(row[2]) if row[2] else f"doc_{row[0]}", # 優先使用全域 ID (轉字串)，否則使用文件 KP ID
                "name": name,
                "mermaid_id": row[3],  # ✅ 傳回 mermaid_id 以便前端對齊
                "category": "extracted", # ✅ 標記為提取，以便前端分組
                "source_name": row[4]    # ✅ 新增來源名稱
            })
        return kps

@router.get("/api/courses/{course_id}/content-knowledge-points", tags=["Courses"])
async def get_content_knowledge_points(
    course_id: int,
    unique_content_ids: List[int] = Query(..., description="教材 ID 列表")
):
    """
    取得與指定教材相關的知識點 (用於摘要與試題生成上下文)
    """
    if not unique_content_ids:
        return []
        
    kps_data = await run_in_db_pool(
        _sync_get_content_knowledge_points, 
        course_id=course_id, 
        unique_content_ids=unique_content_ids
    )
    return kps_data


# ==================== Unit Knowledge Point CRUD ====================

class UnitKPCreate(BaseModel):
    name: str

class UnitKPUpdate(BaseModel):
    name: str


def _sync_get_unit_kps(course_id: int, unit_id: int):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, source_type, source_name, source_id, unit_id
            FROM knowledge_points
            WHERE course_id = :course_id AND unit_id = :unit_id
            ORDER BY display_order ASC, id ASC
        """), {"course_id": course_id, "unit_id": unit_id}).fetchall()

        return [
            {
                "id": r.id,
                "name": r.name,
                "source_type": r.source_type,
                "source_name": r.source_name or ("手動新增" if r.source_type == "manual" else ""),
                "source_id": r.source_id,
                "unit_id": r.unit_id,
            }
            for r in rows
        ]


@router.get("/api/courses/{course_id}/units/{unit_id}/kps", tags=["Knowledge Points"])
async def get_unit_kps(course_id: int, unit_id: int):
    """
    Get all confirmed knowledge points for a unit.
    Includes both manually created KPs and those promoted from document extraction.
    """
    return await run_in_db_pool(_sync_get_unit_kps, course_id, unit_id)


def _sync_create_unit_kp(course_id: int, unit_id: int, name: str):
    with engine.connect() as conn:
        with conn.begin():
            # Check for duplicate name in this course
            existing = conn.execute(text("""
                SELECT id FROM knowledge_points
                WHERE course_id = :course_id AND name = :name
            """), {"course_id": course_id, "name": name}).fetchone()

            if existing:
                raise ValueError(f"知識點「{name}」在此課程中已存在")

            result = conn.execute(text("""
                INSERT INTO knowledge_points
                    (unit_id, course_id, name, display_order, source_type, source_name)
                VALUES
                    (:unit_id, :course_id, :name, 5, 'manual', '手動新增')
                RETURNING id
            """), {"unit_id": unit_id, "course_id": course_id, "name": name})

            new_id = result.scalar()
            return {"id": new_id, "name": name, "source_type": "manual", "source_name": "手動新增", "unit_id": unit_id}


@router.post("/api/courses/{course_id}/units/{unit_id}/kps", tags=["Knowledge Points"])
async def create_unit_kp(course_id: int, unit_id: int, body: UnitKPCreate):
    """
    Manually create a knowledge point for a unit.
    Stored with source_type='manual' so it can be distinguished from extracted KPs.
    """
    try:
        return await run_in_db_pool(_sync_create_unit_kp, course_id, unit_id, body.name.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _sync_update_unit_kp(course_id: int, unit_id: int, kp_id: int, name: str):
    with engine.connect() as conn:
        with conn.begin():
            # Verify ownership
            row = conn.execute(text("""
                SELECT id FROM knowledge_points
                WHERE id = :kp_id AND course_id = :course_id AND unit_id = :unit_id
            """), {"kp_id": kp_id, "course_id": course_id, "unit_id": unit_id}).fetchone()

            if not row:
                raise LookupError("知識點不存在或不屬於此單元")

            # Check name conflict
            conflict = conn.execute(text("""
                SELECT id FROM knowledge_points
                WHERE course_id = :course_id AND name = :name AND id != :kp_id
            """), {"course_id": course_id, "name": name, "kp_id": kp_id}).fetchone()

            if conflict:
                raise ValueError(f"知識點「{name}」在此課程中已存在")

            conn.execute(text("""
                UPDATE knowledge_points SET name = :name WHERE id = :kp_id
            """), {"name": name, "kp_id": kp_id})

            return {"id": kp_id, "name": name}


@router.patch("/api/courses/{course_id}/units/{unit_id}/kps/{kp_id}", tags=["Knowledge Points"])
async def update_unit_kp(course_id: int, unit_id: int, kp_id: int, body: UnitKPUpdate):
    """Rename a knowledge point (works for both manual and extracted KPs)."""
    try:
        return await run_in_db_pool(_sync_update_unit_kp, course_id, unit_id, kp_id, body.name.strip())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _sync_delete_unit_kp(course_id: int, unit_id: int, kp_id: int):
    with engine.connect() as conn:
        with conn.begin():
            # Verify ownership
            row = conn.execute(text("""
                SELECT id, name FROM knowledge_points
                WHERE id = :kp_id AND course_id = :course_id AND unit_id = :unit_id
            """), {"kp_id": kp_id, "course_id": course_id, "unit_id": unit_id}).fetchone()

            if not row:
                raise LookupError("知識點不存在或不屬於此單元")

            # Check if any question_bank entries reference this KP
            linked_count = conn.execute(text("""
                SELECT COUNT(*) FROM question_bank WHERE kp_id = :kp_id AND is_deleted IS NOT TRUE
            """), {"kp_id": kp_id}).scalar()

            conn.execute(text("""
                DELETE FROM knowledge_points WHERE id = :kp_id
            """), {"kp_id": kp_id})

            return {"deleted_kp_id": kp_id, "name": row.name, "linked_questions": linked_count}


@router.delete("/api/courses/{course_id}/units/{unit_id}/kps/{kp_id}", tags=["Knowledge Points"])
async def delete_unit_kp(course_id: int, unit_id: int, kp_id: int):
    """
    Delete a knowledge point.
    Returns the count of questions that were linked to it so the caller can warn the user.
    """
    try:
        return await run_in_db_pool(_sync_delete_unit_kp, course_id, unit_id, kp_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
