
"""
Student Preview Flow Router

處理學生的課前預習流程：
1. 查看 preview content
2. 抽取簡答題
3. 記錄作答
4. LLM 批次評分
5. BERT Mastery 評估
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy import text
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from typing import List, Optional, Dict, Tuple, Any
import json
import os
import re
from datetime import datetime
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.time_utils import get_now_taipei
from openai import OpenAI
from dotenv import load_dotenv
import logging
import uuid
from backend.app.services.fill_in_blank_evaluator import evaluate_fill_in_blank

logger = logging.getLogger(__name__)

from backend.app.utils.db_logger import engine
from pydantic import BaseModel, Field

# 載入環境變數
load_dotenv()

from backend.app.config.settings import settings

# 初始化 OpenAI client
OPENAI_API_KEY = settings.openai_api_key
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    # 這裡的 openai_client 只用來判斷是否可以用 LLM，actual usage moved to service
    openai_client = None

# 導入 Services
from backend.app.services.bert_mastery_service import predict_mastery as bert_predict_mastery
from backend.app.services.lime_explainer_service import explain_mastery
from backend.app.services.question_service import fetch_questions
from backend.app.services.llm_evaluation_service import evaluate_answer_with_llm, generate_question_explanation

router = APIRouter(
    prefix="/api/student",
    tags=["student-preview"]
)

# 沒有已發佈練習題的教材，改用「累積閱讀秒數達門檻」作為完成 fallback 判斷
READING_COMPLETION_THRESHOLD_SECONDS = 30

# ==================== Helper Functions ====================

# ✅ Phase 3: get_current_user_id 已從 auth_utils 導入，移除本地實作


# ============================================================================
# Pydantic Models
# ============================================================================

class PreviewContentResponse(BaseModel):
    """Preview content 回應"""
    knowledge_point_id: int
    knowledge_point_name: str
    unit_name: str
    content_markdown: str
    content_plain: Optional[str] = None
    created_at: str


class QuestionItem(BaseModel):
    """題目資訊"""
    id: int
    question: str
    reference_pages: Optional[str] = None


class QuestionsResponse(BaseModel):
    """題目列表回應"""
    knowledge_point_id: int
    knowledge_point_name: str
    questions: List[QuestionItem]


class QuestionLogRequest(BaseModel):
    """記錄作答請求"""
    question_id: Optional[int] = None  # 可選：內嵌題目不存在於 question_bank
    knowledge_point_id: Optional[int] = None
    course_id: Optional[int] = None
    unit_id: Optional[int] = None
    stage: str  # 'preview' or 'review'
    answer: str = Field(..., min_length=1, description="學生答案（選擇題存選項如'A'，簡答題存完整文字）")
    question_type: Optional[str] = 'short_answer'  # 'multiple_choice' | 'short_answer' | 'true_false'
    correct_answer: Optional[str] = None  # 選擇題的正確答案（用於自動評分）
    question_text: Optional[str] = None  # 內嵌題目的題目文字
    detailed_explanation: Optional[str] = None
    unit_session_id: Optional[uuid.UUID] = None


class QuestionLogResponse(BaseModel):
    """記錄作答回應"""
    log_id: int
    status: str
    message: str


class BatchEvaluateRequest(BaseModel):
    """批次評估請求"""
    log_ids: List[int]


class EvaluationResult(BaseModel):
    """單題評估結果處理"""
    log_id: int
    question_id: int
    correctness: str  # 'correct', 'partially_correct', 'incorrect'
    feedback: str
    explanation: Optional[str] = None
    evaluated_at: str


class BatchEvaluateResponse(BaseModel):
    """批次評估回應"""
    results: List[EvaluationResult]
    summary: dict


class RecommendedQuestionItem(BaseModel):
    """推薦題目項目"""
    id: int
    question: str
    question_type: str = "short_answer"
    knowledge_point_id: int
    knowledge_point_name: str
    reference_pages: Optional[str] = None
    difficulty_level: Optional[str] = None
    detailed_explanation: Optional[str] = None
    source: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, str]] = None
    correct_answer: Optional[str] = None
    sample_answer: Optional[str] = None
    answer: Optional[str] = None
    tags: Optional[List[str]] = None


class RecommendedQuestionsResponse(BaseModel):
    """推薦題目列表回應"""
    questions: List[RecommendedQuestionItem]
    total_count: int


# NOTE: Mastery Schemas have been migrated to student_mastery_router.py
# - MasteryEvaluateRequest
# - MasteryEvaluateResponse
# - MasteryExplanationResponse
# - MasteryItem
# - MasteryListResponse


# ============================================================================
# New Models for Student Content
# ============================================================================

class StudentContentItem(BaseModel):
    """學生端教材/作業項目"""
    id: int
    title: str
    content_type: str  # 'material', 'exam'
    content_subtype: Optional[str] = None  # 'preview', 'review', etc.
    source_type: Optional[str] = None
    content: Any = None  # 實際內容 (ANY type to handle Dict, List, or String)
    knowledge_points: List[dict] = []  # List of {id, name}
    created_at: str
    display_order: Optional[int] = 0
    show_answers_after: Optional[str] = None  # 答案公布時間
    duration_minutes: Optional[int] = None  # 建議閱讀/作答時間 (分鐘)
    is_preview_completed: bool = False  # 預習完成狀態
    is_submitted: bool = False  # 是否已提交 (作業/測驗)
    include_in_grade: bool = False  # 是否計分
    assignment_type: Optional[str] = None  # 'questions' or 'file_upload'
    description: Optional[str] = None  # Assignment description (Markdown)
    end_time: Optional[str] = None  # 繳交截止時間 (ISO format)
    is_expired: bool = False  # 是否已過期
    has_practice_questions: bool = True  # 是否有對應的練習題目
    is_visible: bool = True  # 模擬視角時辨別是否對學生顯示


class StudentUnitContentsResponse(BaseModel):
    """學生端單元內容列表回應"""
    unit_id: int
    unit_name: str
    items: List[StudentContentItem]


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/units/{unit_id}/contents",
    response_model=StudentUnitContentsResponse,
    summary="取得學生單元內容（教材/作業/測驗）"
)
async def get_student_unit_contents(
    unit_id: int,
    student_id: int = Depends(get_current_user_id)
):
    """
    取得指定單元的所有已發布內容
    包含：
    1. 教材 (material): 預習、複習、上傳檔案
    2. 作業 (assignment)
    3. 測驗 (exam)
    
    直接從 course_contents 表讀取，並包含關聯的知識點資訊與預習完成狀態。
    """
    from sqlalchemy import text
    
    with engine.connect() as conn:
        # 1. Check unit exists
        unit_res = conn.execute(
            text("SELECT name FROM course_units WHERE id = :uid"), 
            {"uid": unit_id}
        ).fetchone()
        if not unit_res:
            raise HTTPException(status_code=404, detail="Unit not found")
        unit_name = unit_res[0]

        # 2. Query contents with KPs and mastery status
        # Join logic:
        # - Left join KPs via cckp
        # - Left join student_knowledge_mastery (skm) to check preview_completed
        # - Aggregation should consider if all KPs are completed? Or any?
        #   Let's assume: If content has KPs, it's completed if ALL linked KPs are preview_completed.
        #   If content has NO KPs (e.g. general material), it's always completed (or default True/False?)
        #   Default to False if has KPs and not all done.
        
        query = text("""
            SELECT 
                cc.id,
                cc.title,
                cc.content_type,
                cc.content_subtype,
                cc.source_type,
                cc.content,
                cc.created_at,
                cc.display_order,
                cc.show_answers_after,
                cc.duration_minutes,
                cc.include_in_grade,
                cc.assignment_type,
                cc.description,
                cc.end_time,
                cc.is_visible,
                json_agg(
                    json_build_object(
                        'id', kp.id, 
                        'name', kp.name,
                        'is_completed', (
                            COALESCE(skm.preview_completed, false)
                            OR EXISTS (
                                SELECT 1 FROM student_question_logs sql2
                                WHERE sql2.student_id = :student_id
                                  AND sql2.knowledge_point_id = kp.id
                                  AND sql2.stage = 'preview'
                            )
                        )
                    )
                ) FILTER (WHERE kp.id IS NOT NULL) as kps_status,
                EXISTS (
                    SELECT 1 FROM submissions_assignment sa 
                    WHERE sa.content_id = cc.id AND sa.user_id = :student_id
                ) as has_assignment_submission,
                EXISTS (
                    SELECT 1 FROM submissions_exam se 
                    WHERE se.content_id = cc.id AND se.user_id = :student_id
                ) as has_exam_submission,
                EXISTS (
                    SELECT 1 FROM question_bank qb2
                    JOIN course_content_knowledge_points cckp2 ON qb2.kp_id = cckp2.knowledge_point_id
                    WHERE cckp2.course_content_id = cc.id
                      AND qb2.is_published = true
                      AND qb2.is_deleted IS NOT TRUE
                ) as has_practice_questions,
                (
                    SELECT COALESCE(SUM(arl.reading_time_seconds), 0)
                    FROM attachments att
                    JOIN attachment_reading_logs arl
                        ON arl.attachment_id = att.id AND arl.student_id = :student_id
                    WHERE att.attachable_type = 'material' AND att.attachable_id = cc.id
                ) as reading_seconds,
                EXISTS (
                    SELECT 1 FROM student_content_views scv
                    WHERE scv.student_id = :student_id AND scv.content_id = cc.id
                ) as has_been_viewed
            FROM course_contents cc
            JOIN course_units cu ON cc.unit_id = cu.id
            JOIN courses c ON cu.course_id = c.id
            LEFT JOIN course_content_knowledge_points cckp ON cc.id = cckp.course_content_id
            LEFT JOIN knowledge_points kp ON cckp.knowledge_point_id = kp.id
            LEFT JOIN student_knowledge_mastery skm ON (
                kp.id = skm.knowledge_point_id 
                AND skm.student_id = :student_id
            )
            WHERE cc.unit_id = :unit_id
              AND (
                  (cc.is_visible = true OR cc.is_visible IS NULL)
                  OR (c.teacher_id = :student_id)
                  OR EXISTS (
                      SELECT 1 FROM enrollments WHERE course_id = c.id AND user_id = :student_id AND role = 'ta'
                  )
              )
              AND (cc.start_time IS NULL OR cc.start_time <= :now)
            GROUP BY cc.id
            ORDER BY cc.display_order NULLS LAST, cc.created_at DESC
        """)
        
        rows = conn.execute(query, {"unit_id": unit_id, "student_id": student_id, "now": get_now_taipei()}).fetchall()
        
        items = []
        now = get_now_taipei()
        for row in rows:
            content_val = row[5]
            
            # Check deadline
            end_time = row[13]
            is_expired = False
            if end_time:
                # Ensure timezone awareness matches
                if end_time.tzinfo and not now.tzinfo:
                   is_expired = now.astimezone(end_time.tzinfo) > end_time
                elif not end_time.tzinfo and now.tzinfo:
                   is_expired = now.replace(tzinfo=None) > end_time
                else:
                   is_expired = now > end_time

            
            # 處理 content JSON 解析
            if isinstance(content_val, str):
                try:
                    content_val = json.loads(content_val)
                except:
                    pass # Keep as string if parsing fails
            
            # 處理 Knowledge Points & Completion Logic
            kps_status = row[15] if row[15] else []
            has_practice_questions = bool(row[18])
            reading_seconds = row[19] or 0
            source_type = row[4]
            
            has_practice_questions = bool(row[18])
            reading_seconds = row[19] or 0
            has_been_viewed = bool(row[20])
            source_type = row[4]

            is_completed = False
            
            if kps_status:
                unique_kps = {kp['id']: kp for kp in kps_status}.values()
                kps_data = [{'id': kp['id'], 'name': kp['name']} for kp in unique_kps]
                
                if has_practice_questions:
                    is_completed = all(kp.get('is_completed', False) for kp in unique_kps)
                else:
                    if source_type == 'uploaded_content':
                        is_completed = reading_seconds >= READING_COMPLETION_THRESHOLD_SECONDS
                    else:
                        is_completed = has_been_viewed
            else:
                kps_data = []
                is_completed = True
            
            items.append(StudentContentItem(
                id=row[0],
                title=row[1] or "無標題",
                content_type=row[2],
                content_subtype=row[3],
                source_type=row[4],
                content=content_val,
                knowledge_points=kps_data,
                created_at=str(row[6]),
                display_order=row[7] or 0,
                show_answers_after=str(row[8]) if row[8] else None,
                duration_minutes=row[9],
                is_preview_completed=is_completed,
                is_submitted=bool(row[16] or row[17]),
                include_in_grade=bool(row[10]) if row[10] is not None else False,
                assignment_type=row[11] if row[11] else None,
                description=row[12] if row[12] else None,
                end_time=row[13].isoformat() if row[13] else None,
                is_expired=is_expired,
                has_practice_questions=bool(row[18]),
                is_visible=bool(row[14] if row[14] is not None else True)
            ))

        # --- 處理 Unit 附件 (最後合併) ---
        from sqlalchemy import text as stext
        att_query = stext("""
            SELECT id, file_name, original_file_name, file_type, file_size_bytes, uploaded_at
            FROM attachments
            WHERE attachable_type = 'unit' AND attachable_id = :uid
            ORDER BY uploaded_at ASC
        """)
        att_rows = conn.execute(att_query, {"uid": unit_id}).fetchall()
        
        # 附件預設為「已鎖定」，除非所有預習教材都完成
        # 如果沒有預習教材，則視為不需鎖定
        preview_materials = [m for m in items if m.content_subtype == 'preview']
        all_preview_done = all(m.is_preview_completed for m in preview_materials) if preview_materials else True

        for att in att_rows:
            items.append(StudentContentItem(
                id=att[0] * -1, # 使用負數 ID 區分
                title=att[2] or att[1], # original_file_name
                content_type='material',
                content_subtype='attachment',
                source_type='attachment',
                content={"file_type": att[3], "file_size": att[4]},
                knowledge_points=[],
                created_at=att[5].isoformat() if att[5] else "",
                display_order=999, # 附件放在最後
                is_preview_completed=all_preview_done, # 借用此欄位標記是否可讀取 (鎖定邏輯)
                include_in_grade=False,
                download_url=f"/api/attachments/{att[0]}/view" # 線上瀏覽連結
            ))

        return StudentUnitContentsResponse(
            unit_id=unit_id,
            unit_name=unit_name,
            items=items
        )


@router.get(
    "/kps/{kp_id}/preview-content",
    response_model=PreviewContentResponse,
    summary="取得知識點的 Preview Content"
)
async def get_preview_content(
    kp_id: int,
    student_id: Optional[int] = None
):
    """
    取得指定知識點的 preview 教材內容
    
    邏輯更新 (v2):
    - 改為從 COURSE_CONTENTS 表讀取
    - 支援 content_subtype='preview'
    - 根據 source_type 自動抓取內容 (Generated / Uploaded / Text)
    """
    from sqlalchemy import text
    
    # 查詢 preview content（透過 COURSE_CONTENTS）
    # 優先序：
    # 1. generated_content: 從 GENERATED_CONTENTS 取 content (JSON) -> 解出 markdown
    # 2. uploaded_content: 從 UPLOADED_CONTENTS 取 file_name -> 回傳 file_path json
    # 3. text: 直接取 COURSE_CONTENTS.content (視為 plain text or markdown)
    
    query = text("""
        SELECT 
            cckp.knowledge_point_id,
            kp.name as knowledge_point_name,
            cu.name as unit_name,
            cc.source_type,
            cc.content as cc_content,
            gc.content as gc_content,
            uc.file_name as uc_filename,
            cc.created_at
        FROM course_contents cc
        JOIN course_content_knowledge_points cckp ON cc.id = cckp.course_content_id
        JOIN knowledge_points kp ON cckp.knowledge_point_id = kp.id
        LEFT JOIN course_units cu ON cc.unit_id = cu.id
        LEFT JOIN generated_contents gc ON (cc.source_id = gc.id AND cc.source_type = 'generated_content')
        LEFT JOIN uploaded_contents uc ON (cc.source_id = uc.id AND cc.source_type = 'uploaded_content')
        WHERE cckp.knowledge_point_id = :kp_id
          AND cc.content_subtype = 'preview'
        ORDER BY cc.created_at DESC
        LIMIT 1
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"kp_id": kp_id}).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"找不到知識點 {kp_id} 的 preview content"
        )
    
    # 解析結果
    kp_id_db = result[0]
    kp_name = result[1]
    unit_name = result[2] or "未分類單元"
    source_type = result[3]
    cc_content = result[4] # JSONB or Text specific to implementation
    gc_content = result[5] # JSONB
    uc_filename = result[6]
    created_at = result[7]
    
    final_markdown = ""
    final_plain = ""
    
    if source_type == 'generated_content' and gc_content:
        # 嘗試從 JSON 結構中提取 markdown
        # Case 1: 直接包含 markdown 欄位
        if isinstance(gc_content, dict) and (gc_content.get('markdown') or gc_content.get('content_markdown')):
            final_markdown = gc_content.get('markdown') or gc_content.get('content_markdown')
            
        # Case 2: 結構化 Summary Report (type="summary_report")
        # 結構: {"content": [{"section_title": "...", "content_list": ["..."]}, ...]}
        elif isinstance(gc_content, dict) and isinstance(gc_content.get('content'), list):
            sections = gc_content.get('content', [])
            md_lines = []
            plain_lines = []
            
            # 檢查是否為 exam_questions 誤用到 preview
            if gc_content.get('type') == 'exam_questions':
                 msg = "此內容為測驗題目，請至練習區查看"
                 md_lines.append(f"> ⚠️ {msg}")
                 plain_lines.append(msg)
            else:
                # 正常 Summary 結構轉 Markdown
                for section in sections:
                    if isinstance(section, dict):
                        title = section.get('section_title', '')
                        if title:
                            md_lines.append(f"## {title}")
                            plain_lines.append(f"{title}")
                        
                        items = section.get('content_list', [])
                        if isinstance(items, list):
                            for item in items:
                                md_lines.append(f"- {item}")
                                plain_lines.append(f"• {item}")
                        elif isinstance(items, str):
                            md_lines.append(items)
                            plain_lines.append(items)
                        
                        md_lines.append("") # 空行
                        plain_lines.append("")
            
            final_markdown = "\n".join(md_lines)
            final_plain = "\n".join(plain_lines)
            
        # Case 3: 其他 fallback
        elif isinstance(gc_content, dict):
             final_markdown = str(gc_content.get('content') or gc_content)
        else:
            final_markdown = str(gc_content)
            
    elif source_type == 'uploaded_content' and uc_filename:
        # 檔案型別，回傳連結格式
        # Use ID-based download URL for attachments
        final_markdown = f"![教材預覽](/api/attachments/{row[0]}/download)"
        final_plain = f"[檔案: {uc_filename}]"
        
    elif source_type == 'text':
        # 直接內容
        if cc_content:
            # Check for structured Summary Report
            if isinstance(cc_content, dict) and isinstance(cc_content.get('content'), list):
                sections = cc_content.get('content', [])
                md_lines = []
                plain_lines = []
                
                for section in sections:
                    if isinstance(section, dict):
                        title = section.get('section_title', '')
                        if title:
                            md_lines.append(f"## {title}")
                            plain_lines.append(f"{title}")
                        
                        items = section.get('content_list', [])
                        if isinstance(items, list):
                            for item in items:
                                md_lines.append(f"- {item}")
                                plain_lines.append(f"• {item}")
                        elif isinstance(items, str):
                            md_lines.append(items)
                            plain_lines.append(items)
                        
                        md_lines.append("")
                        plain_lines.append("")
                
                final_markdown = "\n".join(md_lines)
                final_plain = "\n".join(plain_lines)
                
            # cc_content 是 JSONB，可能是字串或其他格式
            elif isinstance(cc_content, str):
                final_markdown = cc_content
                # import re removed
                plain = final_markdown
                plain = re.sub(r'^#{1,6}\s+', '', plain, flags=re.MULTILINE)
                plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
                plain = re.sub(r'\*(.+?)\*', r'\1', plain)
                plain = re.sub(r'`(.+?)`', r'\1', plain)
                plain = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', plain)
                final_plain = plain.strip()
            else:
                # 如果是其他 JSON，嘗試解析
                final_markdown = str(cc_content)
                final_plain = final_markdown # Fallback
            
            # 生成 plain text: 移除 markdown 語法 (only if not already generated)
            if not final_plain and final_markdown:
                 # import re removed
                 plain = final_markdown
                 plain = re.sub(r'^#{1,6}\s+', '', plain, flags=re.MULTILINE)
                 plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
                 plain = re.sub(r'\*(.+?)\*', r'\1', plain)
                 plain = re.sub(r'`(.+?)`', r'\1', plain)
                 plain = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', plain)
                 final_plain = plain.strip()
            plain = final_markdown
            plain = re.sub(r'^#{1,6}\s+', '', plain, flags=re.MULTILINE)  # 移除標題符號
            plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)  # 移除粗體
            plain = re.sub(r'\*(.+?)\*', r'\1', plain)  # 移除斜體
            plain = re.sub(r'`(.+?)`', r'\1', plain)  # 移除行內程式碼
            plain = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', plain)  # 移除連結，保留文字
            final_plain = plain.strip()
        else:
            final_markdown = ""
            final_plain = ""
        
    # 若仍為空，給預設值
    if not final_markdown:
        final_markdown = "*(此教材暫無內容或格式不支援)*"

    return PreviewContentResponse(
        knowledge_point_id=kp_id_db,
        knowledge_point_name=kp_name,
        unit_name=unit_name,
        content_markdown=final_markdown,
        content_plain=final_plain,
        created_at=str(created_at)
    )



@router.get(
    "/kps/{kp_id}/questions",
    response_model=QuestionsResponse,
    summary="取得練習題目（支援指定題與隨機抽題）"
)
async def fetch_questions_api(
    kp_id: int,
    count: int = Query(3, ge=1, le=10),
    exclude_answered: bool = Query(True),
    student_id: int = Depends(get_current_user_id)
):
    """
    取得練習題目
    
    邏輯更新 (v2):
    1. **優先檢查**：是否有教師指定的練習題 (COURSE_CONTENTS, content_subtype='exercise')
    2. **Fallback**：若無指定，則從題庫隨機抽取 (原邏輯)
    
    使用 `question_service` 處理核心邏輯。
    """
    # 呼叫 Service (不傳 mastery_filter, 預設 None)
    questions_data = await fetch_questions(
        kp_id=kp_id,
        student_id=student_id,
        count=count,
        exclude_answered=exclude_answered
    )
    
    if not questions_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到知識點 {kp_id} 的題目或所有題目已作答"
        )
    
    # 轉換為 Pydantic 模型
    return QuestionsResponse(
        knowledge_point_id=kp_id,
        # 取第一題的知識點名稱，若無則為空
        knowledge_point_name=questions_data[0]['knowledge_point_name'],
        questions=[
            QuestionItem(
                id=q['id'],
                question=q['question'],
                reference_pages=q.get('reference_pages')
            ) for q in questions_data
        ]
    )


@router.post(
    "/question-logs",
    response_model=QuestionLogResponse,
    summary="記錄學生作答"
)
async def submit_question_log(
    request: QuestionLogRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    記錄學生的簡答題作答
    
    - **question_id**: 題目 ID
    - **knowledge_point_id**: 知識點 ID
    - **stage**: 階段 ('preview' 或 'review')
    - **answer**: 學生答案
    """
    from sqlalchemy import text
    
    with engine.connect() as conn:
        unit_id = None
        course_id = None

        # 1. 如果有提供 knowledge_point_id，則從 DB 查詢關聯的 unit_id 和 course_id
        if request.knowledge_point_id:
            query = text("""
                SELECT unit_id, course_id
                FROM knowledge_points
                WHERE id = :kp_id
            """)
            
            result = conn.execute(query, {"kp_id": request.knowledge_point_id}).fetchone()
        
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"找不到知識點 {request.knowledge_point_id}"
                )
        
            unit_id, course_id = result
        
        # 2. 如果沒有 knowledge_point_id，則必須提供 course_id 和 unit_id
        else:
            if not request.course_id or not request.unit_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="若無指定知識點，必須提供 course_id 與 unit_id"
                )
            unit_id = request.unit_id
            course_id = request.course_id
    
        # 插入作答記錄
        # 構建答案 JSON，包含題型資訊
        answer_json = {
            'text': request.answer,
            'question_type': request.question_type or 'short_answer',
        }
        
        # 額外資訊：正確答案、題目文字、詳細解析
        if request.correct_answer:
            answer_json['correct_answer'] = request.correct_answer
        if request.question_text:
            answer_json['question_text'] = request.question_text
        if request.detailed_explanation:
            answer_json['detailed_explanation'] = request.detailed_explanation
        
        insert_query = text("""
            INSERT INTO student_question_logs 
            (student_id, question_id, knowledge_point_id, unit_id, course_id, stage, answer, unit_session_id, answered_at)
            VALUES 
            (:student_id, :question_id, :kp_id, :unit_id, :course_id, :stage, CAST(:answer AS jsonb), :sid, :now)
            RETURNING id
        """)
    
        result = conn.execute(insert_query, {
            "student_id": student_id,
            "question_id": request.question_id,
            "kp_id": request.knowledge_point_id,
            "unit_id": unit_id,
            "course_id": course_id,
            "stage": request.stage,
            "answer": json.dumps(answer_json, ensure_ascii=False),
            "sid": request.unit_session_id,
            "now": get_now_taipei()
        })
    
        log_id = result.fetchone()[0]
        conn.commit()
    
        return QuestionLogResponse(
            log_id=log_id,
            status="recorded",
            message="作答已記錄，待批改"
        )


@router.post(
    "/question-logs/batch-evaluate",
    response_model=BatchEvaluateResponse,
    summary="批次評估學生作答（LLM）"
)
async def batch_evaluate_questions(
    request: BatchEvaluateRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    批次評估學生的簡答題作答
    
    - **log_ids**: 作答記錄 ID 列表
    - 使用 LLM 評分，返回每題的 correctness 和 feedback
    """
    from sqlalchemy import text
    from datetime import datetime
    
    with engine.connect() as conn:
        # 1. 批次查詢所有作答記錄
        # 使用 LEFT JOIN 因為內嵌題目可能不存在於 question_bank
        query = text("""
            SELECT 
                sql.id as log_id,
                sql.question_id,
                sql.answer,
                qb.question_data
            FROM student_question_logs sql
            LEFT JOIN question_bank qb ON sql.question_id = qb.id
            WHERE sql.id = ANY(:log_ids)
              AND sql.student_id = :student_id
        """)
        
        results = conn.execute(
        query,
        {"log_ids": request.log_ids, "student_id": student_id}
        ).fetchall()
    
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的作答記錄"
            )
    
        # 2. 準備批次評分
        evaluation_results = []
    
        for row in results:
            log_id = row[0]
            question_id = row[1]
            student_answer_data = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            student_answer = student_answer_data.get('text', '')
            question_type = student_answer_data.get('question_type', 'short_answer')
        
            # question_data 可能為 None（內嵌題目）
            question_data = json.loads(row[3]) if row[3] and isinstance(row[3], str) else (row[3] or {})
            
            # 提取詳細解析，優先從題庫取，若無則從作答記錄取（內嵌題目）
            detailed_explanation = (
                question_data.get('detailed_explanation') or 
                student_answer_data.get('detailed_explanation')
            )
            source_context = (
                question_data.get('source', {}).get('text') or 
                student_answer_data.get('source_context')
            )
            
            # 🔹 根據題型選擇評分方式
            if question_type == 'multiple_choice':
                # 選擇題：自動評分
                correct_answer = question_data.get('correct_answer', '')
                if student_answer and correct_answer and student_answer.strip().upper() == correct_answer.strip().upper():
                    correctness = 'correct'
                    feedback = '答案正確！'
                else:
                    correctness = 'incorrect'
                    feedback = f'答案錯誤。正確答案是 {correct_answer}。'
                
                # 生成詳細解析
                explanation = detailed_explanation or await generate_question_explanation(
                    question=question_data.get('question') or question_data.get('question_text') or '',
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_type=question_type,
                    options=question_data.get('options'),
                    context=source_context
                )
                    
            elif question_type == 'true_false':
                # 是非題：直接比對
                correct_answer = question_data.get('correct_answer', '')
                if student_answer and correct_answer and student_answer.strip().lower() == correct_answer.strip().lower():
                    correctness = 'correct'
                    feedback = '答案正確！'
                else:
                    correctness = 'incorrect'
                    feedback = f'答案錯誤。正確答案是 {correct_answer}。'
                
                explanation = detailed_explanation or await generate_question_explanation(
                    question=question_data.get('question') or question_data.get('question_text') or '',
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_type=question_type,
                    context=source_context
                )

            elif question_type in ['fill_in_blank', 'fill_in_the_blank']:
                # 填空題：智慧比對（正規化 + 模糊匹配）
                correct_answer = question_data.get('correct_answer', '')
                correctness, feedback = evaluate_fill_in_blank(student_answer, correct_answer)
                
                explanation = detailed_explanation or await generate_question_explanation(
                    question=question_data.get('question') or question_data.get('question_text') or '',
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_type=question_type,
                    context=source_context
                )
                    
            else:
                # 簡答題：使用 LLM 評分
                # 優先從 question_data 取得，若無則從 student_answer_data 取得（內嵌題目）
                question_text = (question_data.get('question') or 
                               question_data.get('question_text') or 
                               student_answer_data.get('question_text') or '')
                reference_answer = question_data.get('answer') or question_data.get('sample_answer') or ''
            
                correctness, feedback, explanation = await evaluate_answer_with_llm(
                    question=question_text,
                    reference_answer=reference_answer,
                    student_answer=student_answer
                )
                
                # 若題目未包含詳細解析，則使用生成式解析
                if question_data.get('detailed_explanation'):
                    explanation = question_data.get('detailed_explanation')
        
            evaluation_results.append({
                "log_id": log_id,
                "question_id": question_id,
                "correctness": correctness,
                "feedback": feedback,
                "explanation": explanation
            })
        # 3. 批次更新資料庫
        from backend.app.utils.time_utils import get_now_taipei
        now = get_now_taipei()
        for result in evaluation_results:
            update_query = text("""
                UPDATE student_question_logs
                SET correctness = :correctness,
                feedback = :feedback,
                explanation = :explanation,
                evaluated_at = :evaluated_at
            WHERE id = :log_id
            """)
        
            conn.execute(update_query, {
                "log_id": result["log_id"],
                "correctness": result["correctness"],
                "feedback": result["feedback"],
                "explanation": result["explanation"],
                "evaluated_at": now
            })
    
        conn.commit()
    
        # 4. 統計結果
        summary = {
            "total": len(evaluation_results),
            "correct": sum(1 for r in evaluation_results if r["correctness"] == "correct"),
            "partially_correct": sum(1 for r in evaluation_results if r["correctness"] == "partially_correct"),
            "incorrect": sum(1 for r in evaluation_results if r["correctness"] == "incorrect")
        }
    
    # 5. 組裝回應
    response_results = [
        EvaluationResult(
            log_id=r["log_id"],
            question_id=r["question_id"],
            correctness=r["correctness"],
            feedback=r["feedback"],
            explanation=r.get("explanation"),
            evaluated_at=now.isoformat()
        )
        for r in evaluation_results
    ]
    
    return BatchEvaluateResponse(
        results=response_results,
        summary=summary
    )



# NOTE: Mastery endpoints have been migrated to student_mastery_router.py
# - POST /api/student/mastery/kps/{kp_id}/evaluate
# - GET /api/student/mastery/kps/{kp_id}/explain
# - GET /api/student/mastery/list


# ============================================================================
# Recommended Questions API (課前預習推薦題目)
# ============================================================================

@router.get(
    "/recommended-questions",
    response_model=RecommendedQuestionsResponse,
    summary="根據知識點取得題庫推薦題目"
)
async def get_recommended_questions(
    kp_ids: str = Query(..., description="knowledge_points.id 列表，以逗號分隔的整數"),
    course_id: Optional[int] = Query(None, description="課程 ID，用於判斷是否為實驗課程"),
    question_type: str = Query('short_answer', description="題目類型 (default: short_answer)"),
    count_per_kp: int = Query(2, ge=1, le=5, description="每個知識點抽取的題目數量，預設 2 題"),
    total_max: int = Query(10, ge=1, le=30, description="總共抽取的題目上限數量，預設 10 題"),
    student_id: int = Depends(get_current_user_id)
):
    """
    根據知識點從題庫隨機抽取推薦題目 (短答題)

    - **kp_ids**: knowledge_points.id 列表（逗號分隔整數）
    - **course_id**: 課程 ID，用於判斷是否為實驗課程（實驗課程排除 AI 生成題）
    - **count_per_kp**: 每個知識點抽取的題目數量，預設 2 題

    篩選條件：
    - 只抓取 short_answer 題型
    - 只推薦已發布的題目 (is_published = true)
    - 實驗課程：排除含 'AI生成' 標籤的題目；其他課程：不排除
    - 排除學生已正確作答的題目
    """
    from sqlalchemy import text
    from backend.app.config.settings import settings

    # Parse integer kp_ids from knowledge_points table
    try:
        kp_id_list = [int(kp.strip()) for kp in kp_ids.split(",") if kp.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的知識點 ID 格式，請使用逗號分隔的整數"
        )

    if not kp_id_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請提供至少一個知識點 ID"
        )

    # Determine if this is an experiment course (strict AI exclusion)
    # Support both int and string representation from env
    is_experiment_course = str(course_id) in [str(cid) for cid in settings.experiment_course_ids] if course_id is not None else False
    
    # Debug logging
    logger.debug(f"Course: {course_id}, Is Experiment: {is_experiment_course}, Settings: {settings.experiment_course_ids}")

    ai_exclude_clause = ""
    if is_experiment_course:
        # Strict exclusion: Specifically look for 'AI生成' or 'AI' as a whole tag/word
        # This avoiding false positives with words like "maintain", "tail", "explain", etc.
        ai_exclude_clause = """
            AND NOT (
                EXISTS (
                    SELECT 1 FROM unnest(COALESCE(qb.tags, ARRAY[]::text[])) AS t 
                    WHERE t = 'AI生成' OR t ILIKE 'AI'
                )
            )
        """
        logger.info(f"🧪 Experiment Course {course_id}: Applying precise AI exclusion (AI生成 or AI)")

    with engine.connect() as conn:
        query = text(f"""
            SELECT
                qb.id,
                qb.question_data,
                qb.question_type,
                qb.difficulty_level,
                kp.id as knowledge_point_id,
                kp.name as knowledge_point_name,
                qb.tags
            FROM question_bank qb
            JOIN knowledge_points kp ON qb.kp_id = kp.id
            WHERE qb.kp_id = ANY(:kp_ids)
              AND qb.question_type = :q_type
              AND qb.is_published = true
              AND qb.is_deleted IS NOT TRUE
              {ai_exclude_clause}
              AND qb.id NOT IN (
                  SELECT question_id FROM student_question_logs
                  WHERE student_id = :student_id
                    AND knowledge_point_id = ANY(:kp_ids)
                    AND stage = 'preview'
                    AND correctness = 'correct'
                    AND question_id IS NOT NULL
              )
            ORDER BY
                qb.kp_id,
                RANDOM()
        """)

        results = conn.execute(query, {
            "kp_ids": kp_id_list,
            "q_type": question_type,
            "student_id": student_id
        }).fetchall()
        
        if is_experiment_course:
            logger.info(f"🔍 Recommendation Results for Course {course_id}: Found {len(results)} valid human questions for KPs {kp_id_list}")
            for r in results:
                logger.debug(f"  - QID {r[0]}: Tags={r[6]}")

        
        # 按知識點分組並限制每個知識點的數量
        questions_by_kp: Dict[int, list] = {}
        for row in results:
            kp_id = row[4]
            if kp_id not in questions_by_kp:
                questions_by_kp[kp_id] = []
            
            if len(questions_by_kp[kp_id]) < count_per_kp:
                q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                q_text = q_data.get('question') or q_data.get('question_text') or ''
                ref_pages = q_data.get('reference_pages')
                if not ref_pages and 'source' in q_data and isinstance(q_data['source'], dict):
                    ref_pages = q_data['source'].get('page_number')
                
                questions_by_kp[kp_id].append(RecommendedQuestionItem(
                    id=row[0],
                    question=q_text,
                    question_type=row[2],
                    knowledge_point_id=kp_id,
                    knowledge_point_name=row[5],
                    reference_pages=str(ref_pages) if ref_pages else None,
                    difficulty_level=row[3],
                    detailed_explanation=q_data.get('detailed_explanation'),
                    source=q_data.get('source'),
                    options=q_data.get('options'),
                    correct_answer=q_data.get('correct_answer'),
                    sample_answer=q_data.get('sample_answer'),
                    answer=q_data.get('answer'),
                    tags=row[6]
                ))
        
        # 合併所有題目並隨機打散，限制總數不超過 10 題
        all_questions = []
        for kp_questions in questions_by_kp.values():
            all_questions.extend(kp_questions)
        
        # 隨機打散
        import random
        random.shuffle(all_questions)
        
        # 限制總數
        final_questions = all_questions[:total_max]
        
        return RecommendedQuestionsResponse(
            questions=final_questions,
            total_count=len(final_questions)
        )

@router.get(
    "/kps/logs",
    summary="取得知識點抽取的題目作答記錄"
)
async def get_kp_question_logs(
    kp_ids: str = Query(..., description="knowledge_points.id 列表，逗號分隔"),
    stage: str = Query('preview', description="階段 (preview/review)"),
    student_id: int = Depends(get_current_user_id)
):
    """
    取得學生在指定知識點的作答記錄
    """
    from backend.app.services.question_log_service import get_student_logs
    
    try:
        kp_id_list = [int(kp.strip()) for kp in kp_ids.split(",") if kp.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ID 格式錯誤")
        
    all_logs = []
    for kp_id in kp_id_list:
        logs = await get_student_logs(student_id, kp_id, stage)
        all_logs.extend(logs)
        
    return {"logs": all_logs}


@router.get(
    "/materials/{content_id}/download",
    summary="下載教材檔案 (需完成預習)"
)
async def download_material(
    material_id: int,
    student_id: int = Depends(get_current_user_id)
):
    """
    下載教材檔案
    
    條件：
    1. 教材類型必須是 'material' 且 source_type='uploaded_content'
    2. 學生必須完成該教材關聯的所有知識點的 'preview' 階段 (student_knowledge_mastery.preview_completed = true)
    
    若符合條件，回傳檔案。
    """
    from sqlalchemy import text
    from fastapi.responses import FileResponse
    from pathlib import Path
    import mimetypes
    
    with engine.connect() as conn:
        # 1. 查詢內容資訊與預習完成狀態
        # Join logic similar to get_student_unit_contents
        query = text("""
            SELECT 
                cc.id,
                cc.title,
                cc.source_type,
                cc.content,
                json_agg(
                    json_build_object(
                        'id', kp.id, 
                        'is_completed', (
                            COALESCE(skm.preview_completed, false)
                            OR EXISTS (
                                SELECT 1 FROM student_question_logs sql2
                                WHERE sql2.student_id = :student_id
                                  AND sql2.knowledge_point_id = kp.id
                                  AND sql2.stage = 'preview'
                            )
                        )
                    )
                ) FILTER (WHERE kp.id IS NOT NULL) as kps_status
            FROM course_contents cc
            LEFT JOIN course_content_knowledge_points cckp ON cc.id = cckp.course_content_id
            LEFT JOIN knowledge_points kp ON cckp.knowledge_point_id = kp.id
            LEFT JOIN student_knowledge_mastery skm ON (
                kp.id = skm.knowledge_point_id 
                AND skm.student_id = :student_id
            )
            WHERE cc.id = :content_id
              AND cc.content_type = 'material'
              AND cc.source_type = 'uploaded_content'
            GROUP BY cc.id
        """)
        
        row = conn.execute(query, {
            "content_id": content_id, 
            "student_id": student_id
        }).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="教材不存在或不是上傳的檔案")
            
        title = row[1]
        content_val = row[3]
        kps_status = row[4] if row[4] else []
        
        # 2. Check Permission
        is_completed = False
        if kps_status:
            # Check if ALL linked KPs are completed
            unique_kps = {kp['id']: kp for kp in kps_status}.values()
            is_completed = all(kp.get('is_completed', False) for kp in unique_kps)
        else:
            # If no KPs linked, allow download (generic material)
            is_completed = True
            
        if not is_completed:
            raise HTTPException(status_code=403, detail="請先完成預習任務後再下載")
            
        # 3. Get File Path
        source_id_query = text("SELECT source_id FROM course_contents WHERE id = :cid")
        source_id = conn.execute(source_id_query, {"cid": content_id}).scalar()
        
        if not source_id:
             raise HTTPException(status_code=404, detail="無法找到檔案關聯")

        # Query uploaded_contents
        file_path = None
        file_name = title
        
        uc_row = conn.execute(text("""
            SELECT file_path, file_name 
            FROM uploaded_contents 
            WHERE unique_content_id = :uid 
            ORDER BY id DESC LIMIT 1
        """), {"uid": source_id}).fetchone()
        
        if uc_row:
            file_path = uc_row[0]
            if uc_row[1]: file_name = uc_row[1]
        else:
            # Fallback: try id
            uc_row_id = conn.execute(text("""
                SELECT file_path, file_name 
                FROM uploaded_contents 
                WHERE id = :uid
            """), {"uid": source_id}).fetchone()
            if uc_row_id:
                file_path = uc_row_id[0]
                if uc_row_id[1]: file_name = uc_row_id[1]
    
    print(f"[Download Debug] Found file_path from DB: {file_path}")

    # Use configured paths from settings
    base_uploads = settings.upload_dir
    # Unified base: we check both current and legacy-style structures if needed
    
    # Try multiple strategies to find the file
    final_path = None
    
    # Use configured paths from settings
    base_uploads = settings.upload_dir
    
    # Try multiple strategies to find the file
    final_path = None
    
    # Strategy 1: Check if the filename exists in our unified uploads directory 
    # (This is the most reliable way when paths come from different environments)
    if file_path:
        potential_filename = Path(file_path).name
        potential_path = base_uploads / potential_filename
        if potential_path.exists():
            final_path = str(potential_path)
    
    # Strategy 2: Absolute path from DB (only if it exists and we have permission)
    if not final_path and file_path:
        try:
            path_obj = Path(file_path)
            if path_obj.exists():
                final_path = str(path_obj)
        except Exception:
            pass

    if not final_path:
        raise HTTPException(status_code=404, detail="檔案無法存取或遺失")

    media_type, _ = mimetypes.guess_type(final_path)
    return FileResponse(
        path=final_path,
        filename=file_name,
        media_type=media_type or 'application/octet-stream'
    )

@router.post("/contents/{content_id}/mark-viewed")
async def mark_content_viewed(
    content_id: int,
    student_id: int = Depends(get_current_user_id)
):
    """記錄學生已經打開過這份教材"""
    def _sync_mark(sid, cid):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO student_content_views (student_id, content_id)
                    VALUES (:sid, :cid)
                    ON CONFLICT (student_id, content_id) DO NOTHING
                """),
                {"sid": sid, "cid": cid}
            )
    await run_in_db_pool(_sync_mark, student_id, content_id)
    return {"message": "已記錄"}