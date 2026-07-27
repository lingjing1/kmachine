
from typing import List, Optional, Dict
import json
from sqlalchemy import text
from fastapi import HTTPException, status
from backend.app.utils.db_logger import engine

async def fetch_questions(
    kp_id: int,
    student_id: int,
    count: int = 1,
    exclude_answered: bool = True,
    mastery_filter: Optional[str] = None  # Future use for review mode
) -> List[dict]:
    """
    統一題目抓取邏輯
    
    1. 優先：教師指定題目 (COURSE_CONTENTS, content_subtype='exercise')
    2. Fallback：隨機題庫抽題
    3. 複習模式：根據 mastery_filter 調整題目難度/數量 (To be implemented)
    """
    
    # 1. 嘗試獲取指定題目
    assigned_questions = await get_assigned_questions(kp_id)
    if assigned_questions:
        return assigned_questions
        
    # 2. 若無指定，則隨機抽題
    return await get_random_questions(kp_id, student_id, count, exclude_answered, mastery_filter)


async def get_assigned_questions(kp_id: int) -> Optional[List[dict]]:
    """檢查是否有教師指定題目"""
    with engine.connect() as conn:
        assigned_query = text("""
            SELECT cc.content
            FROM course_contents cc
            JOIN course_content_knowledge_points cckp ON cc.id = cckp.course_content_id
            WHERE cckp.knowledge_point_id = :kp_id
              AND cc.content_subtype = 'exercise'
              AND cc.is_visible = true
            ORDER BY cc.created_at DESC
            LIMIT 1
        """)
        assigned_result = conn.execute(assigned_query, {"kp_id": kp_id}).fetchone()
        
        if assigned_result and assigned_result[0]:
            content_data = assigned_result[0]
            if isinstance(content_data, str):
                try:
                    content_data = json.loads(content_data)
                except:
                    content_data = {}
            
            question_ids = []
            
            # Case A: ID list
            if "question_ids" in content_data:
                question_ids = content_data["question_ids"]
            # Case B: Object list
            elif "questions" in content_data:
                q_list = content_data["questions"]
                if isinstance(q_list, list):
                    question_ids = [q.get("id") for q in q_list if isinstance(q, dict) and q.get("id")]
            
            if question_ids:
                return _get_questions_by_ids(conn, question_ids)
    return None

def _get_questions_by_ids(conn, question_ids: List[int]) -> List[dict]:
    """根據 ID 列表查詢題目詳情"""
    q_query = text("""
        SELECT 
            qb.id,
            qb.question_data,
            kp.name as knowledge_point_name,
            kp.id as kp_id
        FROM question_bank qb
        JOIN knowledge_points kp ON qb.kp_id = kp.id
        WHERE qb.id = ANY(:q_ids)
    """)
    q_results = conn.execute(q_query, {"q_ids": question_ids}).fetchall()
    
    questions = []
    for row in q_results:
        q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        
        # 解析 Question Data (相容多種格式)
        q_text = q_data.get('question') or q_data.get('question_text') or ''
        
        # 解析 Reference Pages
        ref_pages = q_data.get('reference_pages')
        if not ref_pages and 'source' in q_data and isinstance(q_data['source'], dict):
            ref_pages = q_data['source'].get('page_number')
        
        questions.append({
            "id": row[0],
            "question": q_text,
            "reference_pages": ref_pages,
            "knowledge_point_name": row[2],
            "knowledge_point_id": row[3]
        })
    return questions

async def get_random_questions(
    kp_id: int, 
    student_id: int,
    count: int,
    exclude_answered: bool = True,
    mastery_filter: Optional[str] = None
) -> List[dict]:
    """從題庫隨機抽取題目"""
    with engine.connect() as conn:
        # Check unit ID
        unit_query = text("SELECT unit_id FROM knowledge_points WHERE id = :kp_id")
        unit_result = conn.execute(unit_query, {"kp_id": kp_id}).fetchone()
        
        if not unit_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到知識點 {kp_id}"
            )
        
        unit_id = unit_result[0]
        
        # Check quota (Soft limit logic as per v2 requirements)
        # We don't enforce max_unit_questions strictly anymore to ensure at least 1 question
        
        # Check available questions count
        available_query = text("""
            SELECT COUNT(*) FROM question_bank qb
            WHERE qb.kp_id = :kp_id AND qb.question_type = 'short_answer' AND qb.is_published = true
        """)
        available_count = conn.execute(available_query, {"kp_id": kp_id}).scalar()
        
        if available_count == 0:
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"知識點 {kp_id} 沒有可用的題目"
            )
            
        actual_count = min(count, available_count)
        
        # Exclude answered setup
        exclude_clause = ""
        if exclude_answered:
            exclude_clause = """
                AND qb.id NOT IN (
                    SELECT question_id FROM student_question_logs 
                    WHERE student_id = :student_id 
                      AND knowledge_point_id = :kp_id
                      AND stage = 'preview'
                      AND correctness = 'correct'
                )
            """
            
        # Optional: Mastery filter logic (placeholder for future expansion)
        mastery_clause = ""
        # if mastery_filter == '待加強': ...
        
        # Random fetch query
        query = text(f"""
            SELECT 
                qb.id,
                qb.question_data,
                kp.name as knowledge_point_name,
                kp.id as kp_id
            FROM question_bank qb
            JOIN knowledge_points kp ON qb.kp_id = kp.id
            WHERE qb.kp_id = :kp_id
              AND qb.question_type = 'short_answer'
              AND qb.is_published = true
              {exclude_clause}
              {mastery_clause}
            ORDER BY RANDOM()
            LIMIT :count
        """)
        
        results = conn.execute(
            query,
            {"kp_id": kp_id, "student_id": student_id, "count": actual_count}
        ).fetchall()
        
        if not results:
            # If filtered result is empty but available_count > 0, it means all answered correctly
            # We might want to allow re-practice or return empty list depending on requirement.
            # Current logic: return empty list is better than 404 if simply ran out of new questions
            return [] 

        questions = []
        for row in results:
            q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            
            # 解析 Question Data (相容多種格式)
            q_text = q_data.get('question') or q_data.get('question_text') or ''
            
            # 解析 Reference Pages
            ref_pages = q_data.get('reference_pages')
            if not ref_pages and 'source' in q_data and isinstance(q_data['source'], dict):
                ref_pages = q_data['source'].get('page_number')
            
            questions.append({
                "id": row[0],
                "question": q_text,
                "reference_pages": ref_pages,
                "knowledge_point_name": row[2],
                "knowledge_point_id": row[3]
            })
            

        return questions

async def process_content_questions_trigger(content_id: int):
    """
    Trigger: 檢查並處理 Course Content 中的題目
    如果 content 中包含 raw 'questions' 但沒有 'question_ids'，
    則將題目遷移至 Question Bank 並更新 content。
    """
    print(f"Triggering question bank sync for content: {content_id}")
    with engine.connect() as conn:
        # 1. 鎖定並讀取 content
        result = conn.execute(text("""
            SELECT cc.id, cc.course_id, cc.content, cc.content_subtype, cc.content_type, cckp.knowledge_point_id
            FROM course_contents cc
            LEFT JOIN course_content_knowledge_points cckp ON cc.id = cckp.course_content_id
            WHERE cc.id = :cid
            LIMIT 1
        """), {"cid": content_id}).fetchone()
        
        if not result:
            print(f"Content {content_id} not found.")
            return

        row_id, course_id, content, subtype, ctype, kp_id = result
        
        # Determine actual type (prefer content_type if available, else subtype)
        # Note: 'subtype' is often used for 'exercise', 'ctype' for 'assignment'/'exam'
        actual_type = ctype if ctype else subtype
        
        # 確保 content 是 dict
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except:
                print(f"Content {content_id} has invalid JSON.")
                return
        
        if not isinstance(content, dict):
            return


        # 檢查是否需要遷移
        # 條件: 有 'questions' 且 (無 'question_ids' 或為空)
        raw_questions = content.get("questions")
        has_ids = content.get("question_ids")
        
        if raw_questions and isinstance(raw_questions, list) and not has_ids:
            print(f"Processing {len(raw_questions)} questions for Content {content_id} ({subtype})...")
            
            new_question_ids = []
            

            for q_idx, q_item in enumerate(raw_questions):
                if not isinstance(q_item, dict):
                    continue
                
                q_id = None
                # Check if question already has a bank ID (like in Exam format)
                if "saved_question_bank_id" in q_item and q_item["saved_question_bank_id"]:
                    try:
                        q_id = int(q_item["saved_question_bank_id"])
                        print(f"  - Reuse existing Q: {q_id}")
                    except ValueError:
                        q_id = None

                if not q_id:
                    # 準備題庫資料
                    q_text = q_item.get("question") or q_item.get("question_text", "Untitled Question")
                    q_type = q_item.get("type") or q_item.get("question_type", "short_answer")
                    
                    # 插入 Question Bank
                    from backend.app.utils.time_utils import get_now_taipei
                    now = get_now_taipei()
                    insert_q = text("""
                        INSERT INTO question_bank (
                            course_id, creator_id, title, question_data, 
                            question_type, difficulty_level, tags, 
                            unit_id, kp_id, is_published, created_at, updated_at
                        ) VALUES (
                            :course_id, 1, :title, CAST(:q_data AS jsonb),
                            :q_type, NULL, :tags,
                            (SELECT unit_id FROM knowledge_points WHERE id = :kp_id), :kp_id,
                            true, :now, :now
                        )
                        RETURNING id
                    """)
                    
                    # 構建 Title
                    title = f"{subtype}_{content_id}_{q_idx+1}"
                    if len(q_text) > 20:
                        title += f"_{q_text[:10]}..."
                    
                    q_id = conn.execute(insert_q, {
                        "course_id": course_id,
                        "title": title,
                        "q_data": json.dumps(q_item, ensure_ascii=False),
                        "q_type": q_type,
                        "tags": [f"source:content_{content_id}"],
                        "kp_id": kp_id,
                        "now": now
                    }).scalar()
                    print(f"  - Migrated Q: {q_id}")
                
                 # Update usage? The DB trigger handles usage counting based on saved_question_bank_id.
                 # If we just inserted, we might want to BACK-FILL saved_question_bank_id into the raw question 
                 # if we want the trigger to count it? 
                 # Or just rely on question_ids being the new standard.
                 
                new_question_ids.append(q_id)

            # 更新 Content
            if new_question_ids:
                content["question_ids"] = new_question_ids
                
                update_sql = text("""
                    UPDATE course_contents
                    SET content = CAST(:new_content AS jsonb)
                    WHERE id = :cid
                """)
                
                conn.execute(update_sql, {
                    "cid": content_id,
                    "new_content": json.dumps(content, ensure_ascii=False)
                })
                conn.commit()
                print(f"✅ Content {content_id} updated with {len(new_question_ids)} question IDs.")
            else:
                print("No valid questions extracted.")
        else:
            print(f"Content {content_id} does not require migration.")
