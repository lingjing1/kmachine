"""
Question Bank Router: 題庫管理 API
處理題目的 CRUD、搜尋、篩選、以及與 course_contents 的關聯
"""
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id

from backend.app.utils.time_utils import get_now_taipei

logger = logging.getLogger(__name__)

router = APIRouter()

def _safe_int(val):
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

# ==================== Pydantic Schemas ====================

class QuestionBankCreate(BaseModel):
    """建立題庫題目"""
    title: str
    description: Optional[str] = None
    question_data: Dict[str, Any]  # JSONB 完整題目內容
    question_type: str  # multiple_choice, short_answer, true_false, fill_in_blank, matching
    difficulty_level: Optional[str] = None  # easy, medium, hard
    estimated_time_minutes: Optional[int] = None
    tags: Optional[List[str]] = None
    unit_id: Optional[int] = None
    kp_id: Optional[Any] = None

class QuestionBankUpdate(BaseModel):
    """更新題庫題目"""
    title: Optional[str] = None
    description: Optional[str] = None
    question_data: Optional[Dict[str, Any]] = None
    question_type: Optional[str] = None
    difficulty_level: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    tags: Optional[List[str]] = None
    unit_id: Optional[int] = None
    kp_id: Optional[Any] = None

class QuestionBankResponse(BaseModel):
    """題庫題目回應"""
    id: int
    course_id: int
    creator_id: int
    title: str
    description: Optional[str]
    question_data: Dict[str, Any]
    question_type: str
    difficulty_level: Optional[str]
    estimated_time_minutes: Optional[int]
    tags: Optional[List[str]]
    times_used: int
    average_score: Optional[float]
    is_published: bool
    created_at: str
    updated_at: str
    unit_id: Optional[int]
    kp_id: Optional[int]
    unit_name: Optional[str] = None
    topic_id: Optional[int] = None
    kp_name: Optional[str] = None

class AddToQuestionBankRequest(BaseModel):
    """從現有題目加入題庫的請求"""
    title: Optional[str] = None
    difficulty_level: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    unit_id: Optional[int] = None
    kp_id: Optional[int] = None

class BatchAddQuestionsRequest(BaseModel):
    """批次加入題目到作業/考試"""
    question_ids: List[int]
    points: Optional[List[float]] = None  # 可選，個別配分

# ==================== 題庫 CRUD Endpoints ====================

def _sync_get_question_bank(
    course_id: int,
    question_type: str = None,
    difficulty: str = None,
    tags: str = None,
    search: str = None,
    unit_id: int = None,
    kp_id: int = None,
    sort: str = "created_desc",
    page: int = 1,
    per_page: int = 20
):
    with engine.connect() as conn:
        # 建構查詢
        conditions = ["qb.course_id = :course_id", "qb.is_published = true", "qb.is_deleted = false"]
        params = {"course_id": course_id}
        
        # 篩選條件
        if question_type:
            conditions.append("qb.question_type = :q_type")
            params["q_type"] = question_type
            
        if difficulty:
            conditions.append("qb.difficulty_level = :difficulty")
            params["difficulty"] = difficulty
            
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            conditions.append("qb.tags && :tags")  # PostgreSQL array overlap operator
            params["tags"] = tag_list
            
        if search:
            conditions.append("(qb.title ILIKE :search OR qb.description ILIKE :search)")
            params["search"] = f"%{search}%"
        
        if unit_id:
            conditions.append("qb.unit_id = :unit_id")
            params["unit_id"] = unit_id
            
        if kp_id:
            conditions.append("qb.kp_id = :kp_id")
            params["kp_id"] = kp_id
        
        # 排序
        sort_map = {
            "created_desc": "qb.created_at DESC",
            "created_asc": "qb.created_at ASC",
            "times_used_desc": "qb.times_used DESC",
            "difficulty_asc": "CASE qb.difficulty_level WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3 END ASC",
            "difficulty_desc": "CASE qb.difficulty_level WHEN 'hard' THEN 1 WHEN 'medium' THEN 2 WHEN 'easy' THEN 3 END ASC"
        }
        order_by = sort_map.get(sort, "qb.created_at DESC")
        
        # 分頁
        offset = (page - 1) * per_page
        params["limit"] = per_page
        params["offset"] = offset
        
        # 執行查詢
        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT 
                qb.id, qb.course_id, qb.creator_id, qb.title, qb.description,
                qb.question_data, qb.question_type, qb.difficulty_level,
                qb.estimated_time_minutes, qb.tags, qb.times_used,
                qb.average_score, qb.is_published, qb.created_at, qb.updated_at,
                qb.unit_id, qb.kp_id,
                cu.name as unit_name,
                cu.topic_id as topic_id,
                kp.name as kp_name
            FROM question_bank qb
            LEFT JOIN course_units cu ON qb.unit_id = cu.id
            LEFT JOIN knowledge_points kp ON qb.kp_id = kp.id
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """)
        
        rows = conn.execute(query, params).fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "course_id": row.course_id,
                "creator_id": row.creator_id,
                "title": row.title,
                "description": row.description,
                "question_data": row.question_data,
                "question_type": row.question_type,
                "difficulty_level": row.difficulty_level,
                "estimated_time_minutes": row.estimated_time_minutes,
                "tags": row.tags,
                "times_used": row.times_used,
                "average_score": float(row.average_score) if row.average_score else None,
                "is_published": row.is_published,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
                "unit_id": row.unit_id,
                "kp_id": row.kp_id,
                "unit_name": row.unit_name,
                "topic_id": row.topic_id if hasattr(row, 'topic_id') else None,
                "kp_name": row.kp_name
            })
        return results

@router.get("/api/courses/{course_id}/question-bank", response_model=List[QuestionBankResponse], tags=["Question Bank"])
async def get_question_bank(
    course_id: int,
    question_type: Optional[str] = Query(None, description="篩選題型"),
    difficulty: Optional[str] = Query(None, description="篩選難度"),
    tags: Optional[str] = Query(None, description="篩選標籤（逗號分隔）"),
    search: Optional[str] = Query(None, description="搜尋關鍵字"),
    unit_id: Optional[int] = Query(None, description="篩選單元"),
    kp_id: Optional[int] = Query(None, description="篩選知識點"),
    sort: Optional[str] = Query("created_desc", description="排序方式"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000)
):
    """
    取得課程題庫列表（支援搜尋、篩選、分頁）
    """
    results = await run_in_db_pool(
        _sync_get_question_bank,
        course_id=course_id,
        question_type=question_type,
        difficulty=difficulty,
        tags=tags,
        search=search,
        unit_id=unit_id,
        kp_id=kp_id,
        sort=sort,
        page=page,
        per_page=per_page
    )
    return [QuestionBankResponse(**r) for r in results]


@router.get("/api/courses/{course_id}/question-bank/kp-stats", tags=["Question Bank"])
async def get_kp_stats(
    course_id: int,
    kp_names: str = Query(..., description="知識點名稱（逗號分隔）")
):
    """
    統計特定知識點在題庫中的題目數量
    """
    kp_name_list = [n.strip() for n in kp_names.split(",") if n.strip()]
    stats = await run_in_db_pool(_sync_get_kp_stats, course_id, kp_name_list)
    return stats


def _sync_get_kp_stats(course_id: int, kp_names: List[str]):
    with engine.connect() as conn:
        if not kp_names:
            return {}
        
        query = text("""
            SELECT kp.name, COUNT(qb.id) as count
            FROM knowledge_points kp
            LEFT JOIN question_bank qb ON kp.id = qb.kp_id
            WHERE kp.course_id = :cid
              AND kp.name = ANY(:names)
              AND (qb.is_published = true OR qb.id IS NULL)
              AND (qb.is_deleted = false OR qb.id IS NULL)
            GROUP BY kp.name
        """)
        
        results = conn.execute(query, {"cid": course_id, "names": kp_names}).fetchall()
        
        stats = {name: 0 for name in kp_names}
        for row in results:
            stats[row.name] = row.count
            
        return stats


def _sync_create_question(course_id: int, question_data: dict):
    with engine.connect() as conn:
        # 檢查課程是否存在
        course_check = conn.execute(
            text("SELECT id FROM courses WHERE id = :cid"),
            {"cid": course_id}
        ).fetchone()
        
        if not course_check:
            return None, "課程不存在"
        
        import json
        
        insert_query = text("""
            INSERT INTO question_bank (
                course_id, creator_id, title, description, question_data,
                question_type, difficulty_level, estimated_time_minutes, tags,
                unit_id, kp_id, created_at, updated_at
            ) VALUES (
                :course_id, :creator_id, :title, :description, CAST(:question_data AS jsonb),
                :question_type, :difficulty_level, :estimated_time_minutes, :tags,
                :unit_id, :kp_id, :now, :now
            )
            RETURNING id, course_id, creator_id, title, description, question_data,
                      question_type, difficulty_level, estimated_time_minutes, tags,
                      times_used, average_score, is_published, created_at, updated_at,
                      unit_id, kp_id
        """)
        
        # Determine creator_id: prefer passed in ID, fallback to teacher of the course
        creator_id = question_data.get("creator_id")
        if not creator_id:
            teacher_query = text("SELECT teacher_id FROM courses WHERE id = :course_id")
            teacher_res = conn.execute(teacher_query, {"course_id": course_id}).fetchone()
            creator_id = teacher_res[0] if teacher_res else 16 # Fallback to admin if course not found
        
        # If no tags provided, default to 'AI生成'
        # Frontend should pass '手動新增' explicitly for manual questions
        auto_tags = question_data.get("tags") if question_data.get("tags") else ['AI生成']
        
        result = conn.execute(insert_query, {
            "course_id": course_id,
            "creator_id": creator_id,
            "title": question_data["title"],
            "description": question_data["description"],
            "question_data": json.dumps(question_data["question_data"]),
            "question_type": question_data["question_type"],
            "difficulty_level": question_data["difficulty_level"],
            "estimated_time_minutes": question_data["estimated_time_minutes"],
            "tags": auto_tags,
            "unit_id": question_data["unit_id"],
            "kp_id": _safe_int(question_data.get("kp_id")),
            "now": get_now_taipei()
        })
        conn.commit()
        
        row = result.fetchone()
        
        return {
            "id": row.id,
            "course_id": row.course_id,
            "creator_id": row.creator_id,
            "title": row.title,
            "description": row.description,
            "question_data": row.question_data,
            "question_type": row.question_type,
            "difficulty_level": row.difficulty_level,
            "estimated_time_minutes": row.estimated_time_minutes,
            "tags": row.tags,
            "times_used": row.times_used,
            "average_score": float(row.average_score) if row.average_score else None,
            "is_published": row.is_published,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "unit_id": row.unit_id,
            "kp_id": row.kp_id
        }, None

@router.post("/api/courses/{course_id}/question-bank", response_model=QuestionBankResponse, tags=["Question Bank"])
async def create_question(course_id: int, question: QuestionBankCreate, user_id: int = Depends(get_current_user_id)):
    """建立新題目到題庫"""
    question_dict = question.dict()
    question_dict["creator_id"] = user_id
    result, error = await run_in_db_pool(_sync_create_question, course_id, question_dict)
    
    if error:
        raise HTTPException(status_code=404, detail=error)
        
    logger.info(f"✅ Created question bank item: ID={result['id']}, Title='{result['title']}', Course={course_id}")
    return QuestionBankResponse(**result)


def _sync_get_unique_tags(course_id: int):
    with engine.connect() as conn:
        # 使用子查詢展開標籤與更新時間，再進行分組排序
        query = text("""
            SELECT t.tag
            FROM (
                SELECT unnest(tags) as tag, updated_at
                FROM question_bank
                WHERE course_id = :cid AND is_deleted = false
            ) t
            WHERE t.tag IS NOT NULL
            GROUP BY t.tag
            ORDER BY MAX(t.updated_at) DESC
        """)
        
        rows = conn.execute(query, {"cid": course_id}).fetchall()
        
        return [row[0] for row in rows]

@router.get("/api/courses/{course_id}/question-bank/tags", response_model=List[str], tags=["Question Bank"])
async def get_unique_tags(course_id: int):
    """
    取得該課程題庫中所有已使用的標籤（不重複）
    排序：依照該標籤最後一次被更新的時間倒序排列（越新的標籤排越前面）
    """
    return await run_in_db_pool(_sync_get_unique_tags, course_id)

def _sync_get_archived_questions(course_id: int, limit: int, offset: int):
    with engine.connect() as conn:
        query = text("""
            SELECT 
                qb.id, qb.course_id, qb.title, qb.question_type, qb.difficulty_level,
                qb.times_used, qb.deleted_at, qb.tags, qb.unit_id, qb.kp_id,
                cu.name as unit_name,
                kp.name as kp_name
            FROM question_bank qb
            LEFT JOIN course_units cu ON qb.unit_id = cu.id
            LEFT JOIN knowledge_points kp ON qb.kp_id = kp.id
            WHERE qb.course_id = :cid AND qb.is_deleted = true
            ORDER BY qb.deleted_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        rows = conn.execute(query, {
            "cid": course_id,
            "limit": limit,
            "offset": offset
        }).fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "course_id": row.course_id,
                "title": row.title,
                "question_type": row.question_type,
                "difficulty_level": row.difficulty_level,
                "times_used": row.times_used,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
                "tags": row.tags,
                "unit_id": row.unit_id,
                "kp_id": row.kp_id,
                "unit_name": row.unit_name,
                "kp_name": row.kp_name
            })
        return results

@router.get("/api/courses/{course_id}/question-bank/archived", tags=["Question Bank"])
async def get_archived_questions(
    course_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000)
):
    """取得已封存的題目列表"""
    offset = (page - 1) * per_page
    results = await run_in_db_pool(_sync_get_archived_questions, course_id, per_page, offset)
    return results


def _sync_get_question(course_id: int, question_id: int):
    with engine.connect() as conn:
        query = text("""
            SELECT 
                id, course_id, creator_id, title, description, question_data,
                question_type, difficulty_level, estimated_time_minutes, tags,
                times_used, average_score, is_published, created_at, updated_at,
                unit_id, kp_id
            FROM question_bank
            WHERE id = :qid AND course_id = :cid
        """)
        
        row = conn.execute(query, {"qid": question_id, "cid": course_id}).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row.id,
            "course_id": row.course_id,
            "creator_id": row.creator_id,
            "title": row.title,
            "description": row.description,
            "question_data": row.question_data,
            "question_type": row.question_type,
            "difficulty_level": row.difficulty_level,
            "estimated_time_minutes": row.estimated_time_minutes,
            "tags": row.tags,
            "times_used": row.times_used,
            "average_score": float(row.average_score) if row.average_score else None,
            "is_published": row.is_published,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "unit_id": row.unit_id,
            "kp_id": row.kp_id
        }

@router.get("/api/courses/{course_id}/question-bank/{question_id}", response_model=QuestionBankResponse, tags=["Question Bank"])
async def get_question(course_id: int, question_id: int):
    """取得單一題目詳情"""
    result = await run_in_db_pool(_sync_get_question, course_id, question_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="題目不存在")
        
    return QuestionBankResponse(**result)


def _sync_update_question(course_id: int, question_id: int, question_data: dict):
    with engine.connect() as conn:
        # 檢查題目是否存在
        check_query = text("SELECT id FROM question_bank WHERE id = :qid AND course_id = :cid")
        existing = conn.execute(check_query, {"qid": question_id, "cid": course_id}).fetchone()
        
        if not existing:
            return None, "題目不存在"
        
        # 建構更新語句
        updates = []
        params = {"qid": question_id, "cid": course_id}
        
        import json
        
        if question_data.get("title") is not None:
            updates.append("title = :title")
            params["title"] = question_data["title"]
        if question_data.get("description") is not None:
            updates.append("description = :description")
            params["description"] = question_data["description"]
        if question_data.get("question_data") is not None:
            updates.append("question_data = CAST(:question_data AS JSONB)")
            params["question_data"] = json.dumps(question_data["question_data"])
        if question_data.get("question_type") is not None:
            updates.append("question_type = :question_type")
            params["question_type"] = question_data["question_type"]
        if question_data.get("difficulty_level") is not None:
            updates.append("difficulty_level = :difficulty_level")
            params["difficulty_level"] = question_data["difficulty_level"]
        if question_data.get("estimated_time_minutes") is not None:
            updates.append("estimated_time_minutes = :estimated_time_minutes")
            params["estimated_time_minutes"] = question_data["estimated_time_minutes"]
        if question_data.get("tags") is not None:
            updates.append("tags = :tags")
            params["tags"] = question_data["tags"]
        if question_data.get("unit_id") is not None:
            updates.append("unit_id = :unit_id")
            params["unit_id"] = question_data["unit_id"]
        if question_data.get("kp_id") is not None:
            updates.append("kp_id = :kp_id")
            params["kp_id"] = _safe_int(question_data["kp_id"])
        
        if not updates:
            return None, "沒有要更新的欄位"
        
        # updated_at 會由觸發器自動更新
        update_query = text(f"""
            UPDATE question_bank
            SET {", ".join(updates)}
            WHERE id = :qid AND course_id = :cid
            RETURNING id, course_id, creator_id, title, description, question_data,
                      question_type, difficulty_level, estimated_time_minutes, tags,
                      times_used, average_score, is_published, created_at, updated_at,
                      unit_id, kp_id
        """)
        
        result = conn.execute(update_query, params)
        conn.commit()
        
        row = result.fetchone()
        
        return {
            "id": row.id,
            "course_id": row.course_id,
            "creator_id": row.creator_id,
            "title": row.title,
            "description": row.description,
            "question_data": row.question_data,
            "question_type": row.question_type,
            "difficulty_level": row.difficulty_level,
            "estimated_time_minutes": row.estimated_time_minutes,
            "tags": row.tags,
            "times_used": row.times_used,
            "average_score": float(row.average_score) if row.average_score else None,
            "is_published": row.is_published,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "unit_id": row.unit_id,
            "kp_id": row.kp_id
        }, None

@router.put("/api/courses/{course_id}/question-bank/{question_id}", response_model=QuestionBankResponse, tags=["Question Bank"])
async def update_question(course_id: int, question_id: int, question: QuestionBankUpdate):
    """更新題目"""
    result, error = await run_in_db_pool(_sync_update_question, course_id, question_id, question.dict(exclude_unset=True))
    
    if error == "題目不存在":
        raise HTTPException(status_code=404, detail=error)
    elif error == "沒有要更新的欄位":
        raise HTTPException(status_code=400, detail=error)
    elif error:
        raise HTTPException(status_code=500, detail=error)
        
    logger.info(f"✅ Updated question bank item: ID={result['id']}")
    return QuestionBankResponse(**result)


def _sync_delete_or_archive_question(course_id: int, question_id: int, force_delete: bool):
    with engine.connect() as conn:
        # 檢查題目狀態
        check_query = text("""
            SELECT times_used, is_deleted 
            FROM question_bank 
            WHERE id = :qid AND course_id = :cid
        """)
        result = conn.execute(check_query, {"qid": question_id, "cid": course_id}).fetchone()
        
        if not result:
            return None, "題目不存在"
        
        times_used = result.times_used
        
        # 如果有試卷正在使用，返回 409 讓前端決定
        if times_used > 0 and not force_delete:
            return {
                "limit_message": True,
                "message": f"有 {times_used} 份試卷正在使用這個題目",
                "times_used": times_used,
                "suggest_archive": True
            }, "Reference Conflict"
        
        # times_used = 0，永久刪除
        # First, clear saved_question_bank_id references from course_contents
        # Use Python to handle complex nested JSONB structures safely
        import json
        
        find_refs_query = text("""
            SELECT id, content 
            FROM course_contents 
            WHERE course_id = :cid 
            AND content::text LIKE :pattern
        """)
        refs = conn.execute(find_refs_query, {
            "cid": course_id,
            "pattern": f'%"saved_question_bank_id": {question_id}%'
        }).fetchall()
        
        for ref_row in refs:
            content = ref_row.content
            modified = False
            
            def clear_ref_from_items(items):
                nonlocal modified
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            if item.get('saved_question_bank_id') == question_id:
                                del item['saved_question_bank_id']
                                modified = True
                            # Handle nested questions in blocks
                            if 'questions' in item and isinstance(item['questions'], list):
                                clear_ref_from_items(item['questions'])
                            # Handle nested content array
                            if 'content' in item and isinstance(item['content'], list):
                                clear_ref_from_items(item['content'])
                elif isinstance(items, dict):
                    # Handle dict with content key
                    if 'content' in items:
                        clear_ref_from_items(items['content'])
            
            # Handle structure: content (dict) -> content (dict/list) -> content (list) -> questions
            if isinstance(content, dict):
                if 'content' in content:
                    inner = content['content']
                    if isinstance(inner, dict) and 'content' in inner:
                        # Structure: content.content.content = [questions]
                        clear_ref_from_items(inner['content'])
                    elif isinstance(inner, list):
                        # Structure: content.content = [questions]
                        clear_ref_from_items(inner)
                    else:
                        clear_ref_from_items(inner)
            elif isinstance(content, list):
                clear_ref_from_items(content)
            
            if modified:
                update_query = text("""
                    UPDATE course_contents 
                    SET content = :content::jsonb 
                    WHERE id = :id
                """)
                conn.execute(update_query, {
                    "id": ref_row.id,
                    "content": json.dumps(content)
                })
        
        delete_query = text("DELETE FROM question_bank WHERE id = :qid AND course_id = :cid")
        conn.execute(delete_query, {"qid": question_id, "cid": course_id})
        conn.commit()
        
        return {"message": "題目已永久刪除", "question_id": question_id}, None

@router.delete("/api/courses/{course_id}/question-bank/{question_id}", tags=["Question Bank"])
async def delete_or_archive_question(
    course_id: int, 
    question_id: int,
    force_delete: bool = Query(False, description="強制永久刪除（需要 times_used = 0）")
):
    """
    刪除或封存題目
    """
    result, error = await run_in_db_pool(_sync_delete_or_archive_question, course_id, question_id, force_delete)
    
    if error == "題目不存在":
        raise HTTPException(status_code=404, detail=error)
    elif error == "Reference Conflict":
        raise HTTPException(
            status_code=409,
            detail=result
        )
    elif error:
        raise HTTPException(status_code=500, detail=error)
        
    logger.info(f"✅ Permanently deleted question: ID={question_id}, also cleared references from contents")
    return result


def _sync_archive_question(course_id: int, question_id: int):
    with engine.connect() as conn:
        archive_query = text("""
            UPDATE question_bank
            SET is_deleted = true, deleted_at = :now
            WHERE id = :qid AND course_id = :cid AND is_deleted = false
            RETURNING id
        """)
        result = conn.execute(archive_query, {"qid": question_id, "cid": course_id, "now": get_now_taipei()}).fetchone()
        
        if not result:
            return None
        
        conn.commit()
        return result.id

@router.post("/api/courses/{course_id}/question-bank/{question_id}/archive", tags=["Question Bank"])
async def archive_question(course_id: int, question_id: int):
    """封存題目（軟刪除）"""
    result_id = await run_in_db_pool(_sync_archive_question, course_id, question_id)
    
    if not result_id:
        raise HTTPException(status_code=404, detail="題目不存在或已被封存")
        
    logger.info(f"📦 Archived question: ID={question_id}")
    
    return {"message": "題目已封存", "question_id": question_id}


def _sync_restore_question(course_id: int, question_id: int):
    with engine.connect() as conn:
        restore_query = text("""
            UPDATE question_bank
            SET is_deleted = false, deleted_at = NULL
            WHERE id = :qid AND course_id = :cid AND is_deleted = true
            RETURNING id
        """)
        result = conn.execute(restore_query, {"qid": question_id, "cid": course_id}).fetchone()
        
        if not result:
            return None
        
        conn.commit()
        return result.id

@router.post("/api/courses/{course_id}/question-bank/{question_id}/restore", tags=["Question Bank"])
async def restore_question(course_id: int, question_id: int):
    """恢復已封存的題目"""
    result_id = await run_in_db_pool(_sync_restore_question, course_id, question_id)
    
    if not result_id:
        raise HTTPException(status_code=404, detail="找不到已封存的題目")
        
    logger.info(f"♻️  Restored question: ID={question_id}")
    
    return {"message": "題目已恢復", "question_id": question_id}





# ==================== 從現有內容加入題庫 ====================

def _sync_add_question_to_bank(course_id: int, content_id: int, question_index: int, difficulty_level: str, creator_id: int, title_override: str = None):
    with engine.connect() as conn:
        # 1. 取得 course_content 的 content 欄位
        content_query = text("""
            SELECT content FROM course_contents
            WHERE id = :cid AND course_id = :course_id
        """)
        
        content_row = conn.execute(content_query, {
            "cid": content_id,
            "course_id": course_id
        }).fetchone()
        
        if not content_row:
            return None, "內容不存在"
        
        content_data = content_row.content
        if not content_data or "questions" not in content_data:
            return None, "內容中沒有題目"
        
        questions = content_data["questions"]
        if question_index < 0 or question_index >= len(questions):
            return None, f"題目索引 {question_index} 超出範圍"
        
        question = questions[question_index]
        
        # 2. 提取題目資訊
        question_text = question.get("question_text", question.get("question", ""))
        question_type = question.get("question_type", question.get("type", "short_answer"))
        
        # 預設標題
        title = title_override or question_text[:50]
        
        import json
        
        # Determine creator_id: prefer passed in ID, fallback to teacher of the course
        if not creator_id:
            teacher_query = text("SELECT teacher_id FROM courses WHERE id = :course_id")
            teacher_res = conn.execute(teacher_query, {"course_id": course_id}).fetchone()
            creator_id = teacher_res[0] if teacher_res else 16
        
        insert_query = text("""
            INSERT INTO question_bank (
                course_id, creator_id, title, description, question_data,
                question_type, difficulty_level, estimated_time_minutes, 
                unit_id, kp_id, tags, created_at, updated_at
            ) VALUES (
                :course_id, :creator_id, :title, :description, :question_data::jsonb,
                :question_type, :difficulty_level, :estimated_time_minutes,
                :unit_id, :kp_id, :tags, :now, :now
            )
            RETURNING id
        """)
        
        # Auto-assign 'AI生成' tag if not provided
        auto_tags = ['AI生成']
        
        result = conn.execute(insert_query, {
            "course_id": course_id,
            "creator_id": creator_id,
            "title": title,
            "description": None,
            "question_data": json.dumps(question),
            "question_type": question_type,
            "difficulty_level": difficulty_level,
            "estimated_time_minutes": None,
            "unit_id": None,
            "kp_id": None,
            "tags": auto_tags,
            "now": get_now_taipei()
        })
        conn.commit()
        
        row = result.fetchone()
        return row.id, None

@router.post("/api/courses/{course_id}/contents/{content_id}/questions/{question_index}/add-to-bank", tags=["Question Bank"])
async def add_question_to_bank(
    course_id: int,
    content_id: int,
    question_index: int,
    request: AddToQuestionBankRequest,
    user_id: int = Depends(get_current_user_id)
):
    """將 course_content 中的某個題目加入題庫"""
    result_id, error = await run_in_db_pool(
        _sync_add_question_to_bank, 
        course_id, 
        content_id, 
        question_index, 
        request.difficulty_level,
        user_id,
        request.title
    )
    
    if error == "內容不存在":
        raise HTTPException(status_code=404, detail=error)
    elif error:
        raise HTTPException(status_code=400, detail=error)
        
    logger.info(f"✅ Added question to bank from content: Question Bank ID={result_id}, Content ID={content_id}")
    
    return {
        "question_bank_id": result_id,
        "message": "題目已加入題庫"
    }


# ==================== 批次加入題目到作業/考試 ====================

def _sync_batch_add_questions_to_content(course_id: int, content_id: int, question_ids: list, points: list):
    with engine.connect() as conn:
        # 檢查 content 是否存在
        content_check = conn.execute(
            text("SELECT id FROM course_contents WHERE id = :cid AND course_id = :course_id"),
            {"cid": content_id, "course_id": course_id}
        ).fetchone()
        
        if not content_check:
            return None, "內容不存在"
            
        # points check is done in endpoint for clarity, but could be here too
        
        # 批次插入
        added_count = 0
        for idx, question_id in enumerate(question_ids):
            # 檢查題目是否存在
            q_check = conn.execute(
                text("SELECT id FROM question_bank WHERE id = :qid AND course_id = :cid"),
                {"qid": question_id, "cid": course_id}
            ).fetchone()
            
            if not q_check:
                logger.warning(f"Question {question_id} not found, skipping")
                continue
            
            # 檢查是否已經加入
            existing = conn.execute(
                text("SELECT id FROM content_questions WHERE content_id = :cid AND question_id = :qid"),
                {"cid": content_id, "qid": question_id}
            ).fetchone()
            
            if existing:
                logger.warning(f"Question {question_id} already in content {content_id}, skipping")
                continue
            
            # 插入關聯
            points_value = points[idx] if points else None
            display_order = idx + 1
            
            conn.execute(
                text("""
                    INSERT INTO content_questions (content_id, question_id, display_order, points)
                    VALUES (:cid, :qid, :order, :points)
                """),
                {
                    "cid": content_id,
                    "qid": question_id,
                    "order": display_order,
                    "points": points_value
                }
            )
            added_count += 1
        
        conn.commit()
        return added_count, None

@router.post("/api/courses/{course_id}/contents/{content_id}/questions/batch-add", tags=["Question Bank"])
async def batch_add_questions_to_content(
    course_id: int,
    content_id: int,
    request: BatchAddQuestionsRequest
):
    """批次將題庫題目加入作業/考試"""
    
    # Pre-check logic (validation) can stay async if it doesn't touch DB
    if request.points and len(request.points) != len(request.question_ids):
         raise HTTPException(
                status_code=400,
                detail="points 陣列長度必須與 question_ids 相同"
            )

    added_count, error = await run_in_db_pool(
        _sync_batch_add_questions_to_content, 
        course_id, 
        content_id, 
        request.question_ids, 
        request.points
    )
    
    if error:
        raise HTTPException(status_code=404, detail=error)
        
    logger.info(f"✅ Added {added_count} questions to content {content_id}")
    
    return {
        "added_count": added_count,
        "content_id": content_id,
        "question_ids": request.question_ids
    }


def _sync_remove_question_from_content(content_id: int, question_id: int):
    with engine.connect() as conn:
        # 檢查關聯是否存在
        check = conn.execute(
            text("SELECT id FROM content_questions WHERE content_id = :cid AND question_id = :qid"),
            {"cid": content_id, "qid": question_id}
        ).fetchone()
        
        if not check:
            return False
            
        conn.execute(
            text("DELETE FROM content_questions WHERE content_id = :cid AND question_id = :qid"),
            {"cid": content_id, "qid": question_id}
        )
        conn.commit()
        return True

@router.delete("/api/courses/{course_id}/contents/{content_id}/questions/{question_id}", tags=["Question Bank"])
async def remove_question_from_content(course_id: int, content_id: int, question_id: int):
    """從作業/考試移除題目（解除關聯，不刪除題庫題目）"""
    success = await run_in_db_pool(_sync_remove_question_from_content, content_id, question_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="此題目未在此內容中")
        
    return {"message": "已從內容中移除題目"}
        
