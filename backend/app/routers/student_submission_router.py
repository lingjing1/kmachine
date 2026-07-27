"""
Student Submission Router

處理作業和考試的提交，使用 submissions_assignment 和 submissions_exam 表
不依賴 question_bank 外鍵，適合內嵌題目
"""
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel
import json
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei
from sqlalchemy import text
import uuid

from backend.app.utils.db_logger import engine
from backend.app.services.llm_evaluation_service import evaluate_answer_with_llm, generate_question_explanation
from backend.app.services.fill_in_blank_evaluator import evaluate_fill_in_blank

router = APIRouter(
    prefix="/api/student",
    tags=["student-submissions"]
)


# ==================== Helper Functions ====================

# ✅ Phase 3: get_current_user_id 已從 auth_utils 導入，移除本地實作


async def evaluate_question(
    question_text: str,
    question_type: str,
    student_answer: str,
    correct_answer: Optional[str] = None,
    reference_answer: Optional[str] = None,
    detailed_explanation: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    統一的題目評分函數，支援多種題型
    """
    feedback = ""
    correctness = "unknown"
    explanation_to_add = detailed_explanation or ""

    # 標準化題型字串
    q_type = question_type.strip().lower()

    # 1. 選擇題
    if q_type == 'multiple_choice':
        if not correct_answer:
            return 'unknown', '未設定正確答案', explanation_to_add
            
        is_correct = (student_answer.strip().upper() == correct_answer.strip().upper())
        correctness = 'correct' if is_correct else 'incorrect'
        feedback = '答案正確！' if is_correct else f'答案錯誤。正確答案是 {correct_answer}。'
            
        if not explanation_to_add:
            explanation_to_add = await generate_question_explanation(
                question=question_text,
                correct_answer=correct_answer,
                student_answer=student_answer,
                question_type=q_type
            )

    # 2. 是非題
    elif q_type == 'true_false':
        if not correct_answer:
            return 'unknown', '缺少正確答案', explanation_to_add
        
        # 標準化是非題比較
        is_correct = (student_answer.strip().lower() == correct_answer.strip().lower())
        correctness = 'correct' if is_correct else 'incorrect'
        feedback = '答案正確！' if is_correct else f'答案錯誤。正確答案是 {correct_answer}。'

        if not explanation_to_add:
            explanation_to_add = await generate_question_explanation(
                question=question_text,
                correct_answer=correct_answer,
                student_answer=student_answer,
                question_type=q_type
            )

    # 3. 填空題
    elif q_type in ['fill_in_blank', 'fill_in_the_blank']:
        if not correct_answer:
            return 'unknown', '缺少正確答案', explanation_to_add
            
        # 填空題智慧比對（正規化 + 模糊匹配）
        correctness, feedback = evaluate_fill_in_blank(student_answer, correct_answer)

        if not explanation_to_add:
            explanation_to_add = await generate_question_explanation(
                question=question_text,
                correct_answer=correct_answer,
                student_answer=student_answer,
                question_type=q_type
            )

    # 4. 簡答題
    elif q_type == 'short_answer':
        ref_ans = reference_answer or ''
        # 呼叫 LLM 評估 (簡答題解析已在 evaluate_answer_with_llm 處理)
        correctness, feedback, llm_explanation = await evaluate_answer_with_llm(
            question=question_text,
            reference_answer=ref_ans,
            student_answer=student_answer
        )
        if not explanation_to_add:
            explanation_to_add = llm_explanation
    
    else:
        return 'unknown', f'不支援的題型: {q_type}', explanation_to_add

    # 不再統一附加解析到 feedback，而是分開回顯
    return correctness, feedback, explanation_to_add


# ==================== Pydantic Models ====================

class QuestionAnswer(BaseModel):
    """單題答案"""
    question_text: str
    question_type: str  # 'multiple_choice' | 'short_answer' | 'true_false'
    student_answer: str
    correct_answer: Optional[str] = None  # 選擇題/是非題用
    reference_answer: Optional[str] = None  # 簡答題用
    detailed_explanation: Optional[str] = None
    options: Optional[Dict[str, Any]] = None  # [NEW] 選擇題選項
    reference_pages: Optional[str] = None    # [NEW] 參考頁碼


class SubmissionRequest(BaseModel):
    """提交請求"""
    answers: List[QuestionAnswer]
    started_at: Optional[str] = None  # 考試開始時間（ISO格式）
    unit_session_id: Optional[uuid.UUID] = None # [NEW] 學習路徑 Session ID


class QuestionResult(BaseModel):
    """單題評分結果處理"""
    question_text: str
    question_type: str
    student_answer: str
    correctness: str  # 'correct' | 'incorrect' | 'partially_correct'
    feedback: str
    explanation: Optional[str] = None
    options: Optional[Dict[str, Any]] = None  # [NEW] 選擇題選項
    reference_pages: Optional[str] = None    # [NEW] 參考頁碼


class SubmissionResponse(BaseModel):
    """提交回應"""
    submission_id: int
    grade: Optional[float] = None
    score: Optional[float] = None
    percentage: Optional[float] = None
    feedback: Optional[str] = None
    is_manual: bool = False
    results: List[QuestionResult]


class PreviousSubmissionResponse(BaseModel):
    """歷史提交記錄回應"""
    submission_id: int
    content_id: int
    score: Optional[float] = None
    submitted_at: Optional[str] = None
    time_spent_minutes: Optional[int] = None
    can_retry: bool = True
    show_answers: bool = True
    include_in_grade: bool = False
    is_manual: bool = False
    results: List[QuestionResult]


# ==================== API Endpoints ====================

@router.get(
    "/submissions/{content_id}",
    response_model=PreviousSubmissionResponse,
    summary="取得歷史提交記錄"
)
async def get_submission(
    content_id: int,
    student_id: int = Depends(get_current_user_id)
):
    """
    取得學生最新的提交記錄
    
    - 根據 content_subtype 決定查詢表
    - homework → submissions_assignment
    - quiz/midterm/final → submissions_exam
    - 回傳最新一筆（updated_at DESC）
    """
    with engine.connect() as conn:
        # 1. 取得 content 資訊
        cc_row = conn.execute(text("""
            SELECT content_subtype, show_answers_after, include_in_grade
            FROM course_contents WHERE id = :id
        """), {"id": content_id}).fetchone()
        
        if not cc_row:
            raise HTTPException(status_code=404, detail="Content not found")
        
        content_subtype = cc_row[0]
        show_answers_after = cc_row[1]
        include_in_grade = bool(cc_row[2]) if cc_row[2] is not None else False
        
        # 2. 根據 content_subtype 決定查詢表
        if content_subtype == 'homework':
            row = conn.execute(text("""
                SELECT id, score, submitted_at, time_spent_minutes, grade, is_manual
                FROM submissions_assignment
                WHERE content_id = :cid AND user_id = :uid
                ORDER BY updated_at DESC LIMIT 1
            """), {"cid": content_id, "uid": student_id}).fetchone()
            can_retry = True
        else:
            # quiz / midterm / final
            row = conn.execute(text("""
                SELECT id, score, submitted_at, time_spent_minutes, grade, is_manual
                FROM submissions_exam
                WHERE content_id = :cid AND user_id = :uid
                ORDER BY updated_at DESC LIMIT 1
            """), {"cid": content_id, "uid": student_id}).fetchone()
            can_retry = False
        
        if not row:
            raise HTTPException(status_code=404, detail="No submission found")
        
        submission_id = row[0]
        score = row[1]
        submitted_at = str(row[2]) if row[2] else None
        time_spent_minutes = row[3]
        grade_json = row[4]
        is_manual = bool(row[5]) if row[5] is not None else False
        
        # 3. 判斷答案是否可見
        show_answers = True
        if content_subtype in ['quiz', 'midterm', 'final'] and show_answers_after:
            now = get_now_taipei()
            target_time = show_answers_after
            if isinstance(target_time, str):
                try:
                    target_time = datetime.fromisoformat(target_time)
                except:
                    pass
            if isinstance(target_time, datetime) and get_now_taipei() < target_time:
                show_answers = False
        
        # 4. 解析 grade JSON 為 results
        results = []
        if grade_json:
            grade_list = grade_json if isinstance(grade_json, list) else json.loads(grade_json)
            for item in grade_list:
                if show_answers:
                    results.append(QuestionResult(
                        question_text=item.get("question_text", ""),
                        question_type=item.get("question_type", "short_answer"),
                        student_answer=item.get("student_answer", ""),
                        correctness=item.get("correctness", "incorrect"),
                        feedback=item.get("feedback", ""),
                        explanation=item.get("explanation"),
                        options=item.get("options"),
                        reference_pages=item.get("reference_pages")
                    ))
                else:
                    # 隱藏答案細節與成績
                    results.append(QuestionResult(
                        question_text=item.get("question_text", ""),
                        question_type=item.get("question_type", "short_answer"),
                        student_answer=item.get("student_answer", ""),
                        correctness="hidden",
                        feedback="尚未到公佈時間",
                        explanation=None,
                        options=item.get("options") # Options are safe to show usually
                    ))
        
        return PreviousSubmissionResponse(
            submission_id=submission_id,
            content_id=content_id,
            score=score if show_answers and include_in_grade else None,
            submitted_at=submitted_at,
            time_spent_minutes=time_spent_minutes,
            can_retry=can_retry,
            show_answers=show_answers,
            include_in_grade=include_in_grade,
            is_manual=is_manual,
            results=results
        )


@router.post(
    "/assignments/{content_id}/submit",
    response_model=SubmissionResponse,
    summary="提交作業"
)
async def submit_assignment(
    content_id: int,
    request: SubmissionRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    提交作業答案並評分
    
    - **content_id**: course_contents.id
    - **answers**: 所有題目的答案
    """
    return await _process_submission(content_id, request, student_id)


@router.post(
    "/exams/{content_id}/submit",
    response_model=SubmissionResponse,
    summary="提交考試"
)
async def submit_exam(
    content_id: int,
    request: SubmissionRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    提交考試答案並評分
    
    - **content_id**: course_contents.id
    - **answers**: 所有題目的答案
    - **started_at**: 考試開始時間（ISO格式）
    """
    return await _process_submission(content_id, request, student_id)


async def _process_submission(
    content_id: int,
    request: SubmissionRequest,
    student_id: int
) -> SubmissionResponse:
    # student_id is now passed from the caller (who uses Depends(get_current_user_id))
    print(f"DEBUG: Processing submission for user={student_id}, content={content_id}")
    
    # 1. 獲取內容資訊 (包含 grading config & subtype)
    with engine.connect() as conn:
        query = text("""
            SELECT content, content_subtype, content_type, show_answers_after, include_in_grade, question_grading
            FROM course_contents 
            WHERE id = :id
        """)
        row = conn.execute(query, {"id": content_id}).fetchone()
        
        if not row:
            print("DEBUG: Content not found!")
            raise HTTPException(status_code=404, detail="Content not found")
            
        content_json = row[0]
        content_subtype = row[1]
        content_type = row[2]
        show_answers_after = row[3]
        include_in_grade = row[4]
        question_grading = row[5] or {}
        print(f"DEBUG: Content found. Type='{content_type}', Subtype='{content_subtype}', include_in_grade={include_in_grade}")
    print(f"DEBUG: Question Grading Config: {json.dumps(question_grading, ensure_ascii=False)}")

    # 2. 評估所有題目
    results = []
    
    for answer in request.answers:
        correctness, feedback, explanation = await evaluate_question(
            question_text=answer.question_text,
            question_type=answer.question_type,
            student_answer=answer.student_answer,
            correct_answer=answer.correct_answer,
            reference_answer=answer.reference_answer,
            detailed_explanation=answer.detailed_explanation
        )
        
        results.append({
            "question_text": answer.question_text,
            "question_type": answer.question_type,
            "student_answer": answer.student_answer,
            "correct_answer": answer.correct_answer,
            "correctness": correctness,
            "feedback": feedback,
            "explanation": explanation,
            "options": answer.options,
            "reference_pages": answer.reference_pages
        })
    
    # 3. 計算總分與成績 (僅在 include_in_grade 為 True 時計算)
    total_score = 0.0
    max_score = 0.0
    percentage = 0.0
    
    if include_in_grade:
        grade_info = calculate_submission_score(results, question_grading)
        total_score = grade_info["total_score"]
        max_score = grade_info["max_score"]
        percentage = (total_score / max_score * 100) if max_score > 0 else 0.0
    
    print(f"DEBUG: include_in_grade={include_in_grade}, Calculated Score={total_score}/{max_score} ({percentage}%)")

    # 準備回傳給前端的結果 (可能需要隱藏答案)
    # Shallow copy dicts is enough as we modify string values
    import copy
    response_results = [r.copy() for r in results] 
    
    should_hide_answers = False
    # User Request: Only check for quiz, midterm, final
    if content_subtype in ['quiz', 'midterm', 'final'] and show_answers_after:
        now = get_now_taipei()
        target_time = show_answers_after
        if isinstance(target_time, str):
            try:
                target_time = datetime.fromisoformat(target_time)
            except:
                pass
        
        if isinstance(target_time, datetime) and now < target_time:
            should_hide_answers = True
            print(f"DEBUG: Hiding answers. Now={now}, RevealAt={target_time}")
            
    if should_hide_answers:
        for r in response_results:
             if "正確答案是" in r.get("feedback", ""):
                 r["feedback"] = "答案錯誤。（正確答案將於公布後顯示）"
             if "correct_answer" in r:
                 r["correct_answer"] = "（公布後顯示）"
    
    # 4. 儲存提交紀錄
    with engine.begin() as conn:
        result_content_json = {
            "questions": results,
            "total_score": total_score,
            "max_score": max_score,
            "total_questions": len(results),
            "correct": sum(1 for r in results if r["correctness"] == "correct"),
            "partially_correct": sum(1 for r in results if r["correctness"] == "partially_correct")
        }

        # 準備詳細評分資料 (JSON)
        grading_details = [
            {
                "question_text": r["question_text"],
                "student_answer": r["student_answer"],
                "correct_answer": r.get("correct_answer"),
                "correctness": r["correctness"],
                "feedback": r["feedback"],
                "question_type": r["question_type"],
                "explanation": r.get("explanation"),
                "options": r.get("options"),
                "reference_pages": r.get("reference_pages")
            }
            for r in results
        ]

        # 計算作答時間 (通用)
        started_at_dt = None
        time_spent_minutes = None
        if request.started_at:
            try:
                started_at_dt = datetime.fromisoformat(request.started_at.replace('Z', '+00:00'))
                time_spent_minutes = int((get_now_taipei() - started_at_dt.replace(tzinfo=None)).total_seconds() / 60)
            except:
                started_at_dt = get_now_taipei()
                time_spent_minutes = 0

        # [NEW] 紀錄詳細的學生答題日誌 (student_question_logs) 並關聯 Session
        from backend.app.services.question_log_service import create_question_log
        for r in results:
            # 簡答題等可能沒有 kp_id，但在這裡我們需要儘量關聯
            # [TODO] 從內容中反查 kp_id (如果有的話)
            # 目前先放寬 question_log_service 的 kp_id 檢核 或 傳入 0
            try:
                # 嘗試從結果中獲取 kp_id (如果有的話)
                kp_id = 0 # Default fallback
                
                await create_question_log(
                    student_id=student_id,
                    question_id=None,
                    knowledge_point_id=kp_id,
                    stage="preview",
                    answer=r["student_answer"],
                    question_type=r["question_type"],
                    correct_answer=r.get("correct_answer"),
                    question_text=r["question_text"],
                    detailed_explanation=r.get("explanation"),
                    unit_session_id=request.unit_session_id,
                    unit_id=None, # [TODO] Get unit_id if possible
                    course_id=content_id # In this router context, content_id is course_content.id which often maps to course context
                )
            except Exception as e:
                print(f"DEBUG: Failed to log individual question: {e}")

        if content_subtype == 'homework':
            # 寫入 submissions_assignment
            insert_query = text("""
                INSERT INTO submissions_assignment 
                (user_id, content_id, content, score, grade, started_at, time_spent_minutes, submitted_at, updated_at)
                VALUES 
                (:user_id, :content_id, CAST(:content AS json), :score, CAST(:grade AS json), :started_at, :time_spent, :now, :now)
                ON CONFLICT ON CONSTRAINT uq_submissions_assignment_content_user
                DO UPDATE SET
                    score = CASE WHEN submissions_assignment.is_manual THEN submissions_assignment.score ELSE EXCLUDED.score END,
                    grade = CASE WHEN submissions_assignment.is_manual THEN submissions_assignment.grade ELSE EXCLUDED.grade END,
                    content = EXCLUDED.content,
                    started_at = EXCLUDED.started_at,
                    time_spent_minutes = EXCLUDED.time_spent_minutes,
                    submitted_at = :now,
                    updated_at = :now
                RETURNING id
            """)
            
            res = conn.execute(insert_query, {
                "user_id": student_id,
                "content_id": content_id,
                "content": json.dumps(result_content_json),
                "score": total_score,
                "grade": json.dumps(grading_details),
                "started_at": started_at_dt,
                "time_spent": time_spent_minutes,
                "now": get_now_taipei()
            })
            submission_id = res.fetchone()[0]
            
        else:
            # 寫入 submissions_exam
            insert_query = text("""
                INSERT INTO submissions_exam 
                (user_id, content_id, content, score, grade,
                 started_at, submitted_at, created_at, updated_at, time_spent_minutes, status, is_late)
                VALUES 
                (:user_id, :content_id, CAST(:content AS json), :score, CAST(:grade AS json),
                 :started_at, :now, :now, :now, :time_spent, 'completed', FALSE)
                ON CONFLICT ON CONSTRAINT uq_submissions_exam_content_user 
                DO UPDATE SET
                    score = CASE WHEN submissions_exam.is_manual THEN submissions_exam.score ELSE EXCLUDED.score END,
                    grade = CASE WHEN submissions_exam.is_manual THEN submissions_exam.grade ELSE EXCLUDED.grade END,
                    content = EXCLUDED.content,
                    submitted_at = :now,
                    updated_at = :now,
                    time_spent_minutes = EXCLUDED.time_spent_minutes,
                    status = 'completed'
                RETURNING id
            """)
            
            res = conn.execute(insert_query, {
                "user_id": student_id,
                "content_id": content_id,
                "content": json.dumps(result_content_json),
                "score": total_score,
                "grade": json.dumps(grading_details),
                "started_at": started_at_dt,
                "time_spent": time_spent_minutes,
                "now": get_now_taipei()
            })
            submission_id = res.fetchone()[0]
            
    return SubmissionResponse(
        submission_id=submission_id,
        score=total_score,
        is_manual=False, # New submission starts as AI-graded
        results=[QuestionResult(**r) for r in response_results]
    )

def calculate_submission_score(results: List[dict], grading_config: dict) -> dict:
    total_score = 0.0
    max_score = 0.0
    
    method = grading_config.get("grading_method", "by_question_type")
    
    type_points_map = {}
    if method == "by_question_type":
        for qt in grading_config.get("question_types", []):
            type_points_map[qt["type_id"]] = float(qt.get("points_per_question", 0))
            
    individual_points_map = {}
    if method == "individual_questions" or method == "by_individual_question":
        for iq in grading_config.get("individual_questions", []):
            if "text" in iq:
                key = iq["text"].strip()
                individual_points_map[key] = float(iq.get("points", 0))
    
    for r in results:
        q_type = r["question_type"]
        q_text = r["question_text"]
        correctness = r["correctness"]
        
        points_assigned = 0.0
        
        if method == "by_question_type":
            # 優先從 mapping 獲取，若無則給予預設值 (避免總分為 0)
            points_assigned = type_points_map.get(q_type, 1.0)
        elif method == "individual_questions" or method == "by_individual_question":
            # 題目文字精確匹配 (忽略前後空格)
            key = q_text.strip()
            points_assigned = individual_points_map.get(key, 1.0)
            if key not in individual_points_map:
                print(f"DEBUG: Scoring mismatch - Question text not found in individual_questions: '{key}'")
            
        max_score += points_assigned
        
        if correctness == "correct":
            total_score += points_assigned
        elif correctness == "partially_correct":
            total_score += (points_assigned * 0.9)
            
        print(f"DEBUG: Question: '{q_text[:20]}...', Points: {points_assigned}, Result: {correctness}")
            
    return {
        "total_score": total_score,
        "max_score": max_score
    }
