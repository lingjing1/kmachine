"""
Student Review Router

處理學生課後複習流程：
1. 取得複習摘要（班級/個人弱項）
2. 取得複習題目
3. 記錄複習作答
4. 批次評估複習作答
5. 提交複習測驗
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Tuple
from datetime import datetime
import uuid
from sqlalchemy import text
from backend.app.utils.time_utils import get_now_taipei

from backend.app.utils.db_logger import engine
from backend.app.services.review_service import review_service
from backend.app.services.question_service import fetch_questions
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.services.fill_in_blank_evaluator import evaluate_fill_in_blank
from backend.app.services.question_log_service import (
    create_question_log,
    batch_evaluate_logs,
    get_student_logs
)
from backend.app.services.challenge_log_service import (
    submit_and_evaluate_challenges,
    ChallengeAnswerItem,
    get_challenge_history,
)


router = APIRouter(
    prefix="/api/student/review",
    tags=["student-review"]
)


# ==================== Helper Functions ====================

# ✅ Phase 3: get_current_user_id 已從 auth_utils 導入，移除本地實作


# ==================== Pydantic Models ====================


class QuestionItem(BaseModel):
    """題目項目"""
    id: int
    question: str
    reference_pages: Optional[str] = None
    difficulty: Optional[str] = None
    source: str = "random"


class QuestionsResponse(BaseModel):
    """題目列表回應"""
    knowledge_point_id: int
    questions: List[QuestionItem]


class QuestionLogRequest(BaseModel):
    """作答記錄請求"""
    question_id: int
    knowledge_point_id: int
    answer: str = Field(..., min_length=1, description="學生答案（不可為空）")
    unit_session_id: Optional[uuid.UUID] = None


class QuestionLogResponse(BaseModel):
    """作答記錄回應"""
    log_id: int
    status: str = "recorded"


class BatchEvaluateRequest(BaseModel):
    """批次評估請求"""
    log_ids: List[int]


class EvaluationResult(BaseModel):
    """單題評估結果處理"""
    log_id: int
    question_id: int
    correctness: str
    feedback: str
    explanation: Optional[str] = None
    evaluated_at: str


class BatchEvaluateResponse(BaseModel):
    """批次評估回應"""
    results: List[EvaluationResult]
    summary: dict


# ==================== Challenge Log Models ====================

class ChallengeAnswerRequest(BaseModel):
    """單題挑戰作答"""
    question_id: int
    knowledge_point_id: int
    answer: str = Field(..., min_length=1)
    difficulty_level: Optional[str] = None
    question_type: Optional[str] = 'short_answer'
    question_text: Optional[str] = None

class SubmitChallengesRequest(BaseModel):
    """挑戰題批次繳交請求（含所有作答）"""
    answers: List[ChallengeAnswerRequest]

class ChallengeEvaluationResult(BaseModel):
    """單題挑戰評估結果"""
    log_id: int
    question_id: int
    correctness: str
    feedback: str
    explanation: Optional[str] = None
    evaluated_at: str

class SubmitChallengesResponse(BaseModel):
    """挑戰題批次繳交回應"""
    results: List[ChallengeEvaluationResult]
    summary: dict


# ==================== API Endpoints ====================


@router.get(
    "/kps/{kp_id}/questions",
    response_model=QuestionsResponse,
    summary="取得複習題目"
)
async def get_review_questions(
    kp_id: int,
    count: int = 2,
    student_id: int = Depends(get_current_user_id)
):
    """
    取得複習題目
    
    優先返回學生之前做錯的題目，不足時補充隨機題目
    """
    
    # 使用 question_service 獲取題目（帶 mastery_filter）
    questions = await fetch_questions(
        kp_id=kp_id,
        student_id=student_id,
        count=count,
        exclude_answered=False,  # 複習模式允許重做題目
        mastery_filter="review"
    )
    
    return QuestionsResponse(
        knowledge_point_id=kp_id,
        questions=[
            QuestionItem(
                id=q["id"],
                question=q["question"],
                reference_pages=q.get("reference_pages"),
                difficulty=q.get("difficulty"),
                source=q.get("source", "random")
            )
            for q in questions
        ]
    )


@router.post(
    "/question-logs",
    response_model=QuestionLogResponse,
    summary="記錄複習作答"
)
async def create_review_question_log(
    request: QuestionLogRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    記錄學生的複習作答
    """
    
    log_id = await create_question_log(
        student_id=student_id,
        question_id=request.question_id,
        knowledge_point_id=request.knowledge_point_id,
        stage="review",  # 固定為 review
        answer=request.answer,
        question_type=request.question_type if hasattr(request, 'question_type') else 'short_answer',
        correct_answer=request.correct_answer if hasattr(request, 'correct_answer') else None,
        question_text=request.question_text if hasattr(request, 'question_text') else None,
        detailed_explanation=request.detailed_explanation if hasattr(request, 'detailed_explanation') else None,
        unit_session_id=request.unit_session_id
    )
    
    return QuestionLogResponse(log_id=log_id, status="recorded")


@router.post(
    "/question-logs/batch-evaluate",
    response_model=BatchEvaluateResponse,
    summary="批次評估複習作答"
)
async def batch_evaluate_review(
    request: BatchEvaluateRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    使用 LLM 批次評估複習作答
    """
    from backend.app.services.llm_evaluation_service import evaluate_answer_with_llm, generate_question_explanation

    # 1. 取得 Log 詳細資訊
    logs_query = text("""
        SELECT 
            sql.id, 
            sql.question_id, 
            sql.student_answer,
            qb.question_data,
            qb.question_type
        FROM student_question_logs sql
        LEFT JOIN question_bank qb ON sql.question_id = qb.id
        WHERE sql.id = ANY(:log_ids)
    """)
    
    evaluation_results = []
    
    with engine.connect() as conn:
        logs = conn.execute(logs_query, {"log_ids": request.log_ids}).fetchall()
        
        for log in logs:
            log_id = log.id
            question_id = log.question_id
            student_answer = log.student_answer
            question_type = log.question_type
            
            # question_data 可能為 None
            question_data = json.loads(log.question_data) if log.question_data and isinstance(log.question_data, str) else (log.question_data or {})

            # 🔹 根據題型選擇評分方式
            correctness = "unknown"
            feedback = ""
            
            # 提取詳細解析與教材脈絡，如果存在 (優先從題庫取，若無則從作答記錄取)
            detailed_explanation = (
                question_data.get('detailed_explanation') or 
                student_answer_data.get('detailed_explanation')
            )
            source_context = (
                question_data.get('source', {}).get('text') or 
                student_answer_data.get('source_context')
            )

            if question_type == 'multiple_choice':
                # 選擇題：自動評分
                correct_answer = question_data.get('correct_answer', '')
                if student_answer and correct_answer and student_answer.strip().upper() == correct_answer.strip().upper():
                    correctness = 'correct'
                    feedback = '答案正確！'
                else:
                    correctness = 'incorrect'
                    feedback = f'答案錯誤。正確答案是 {correct_answer}。'
                
                # 生成詳細解析 (優先使用既有解析)
                explanation = detailed_explanation or await generate_question_explanation(
                    question=question_text,
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
                    question=question_text,
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_type=question_type,
                    context=source_context
                )

            elif question_type == 'fill_in_blank':
                # 填空題：智慧比對（正規化 + 模糊匹配）
                correct_answer = question_data.get('correct_answer', '')
                correctness, feedback = evaluate_fill_in_blank(student_answer, correct_answer)

                explanation = detailed_explanation or await generate_question_explanation(
                    question=question_text,
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_type=question_type,
                    context=source_context
                )

            elif question_type == 'short_answer':
                # 簡答題：LLM 評分
                question_text = (question_data.get('question') or 
                               question_data.get('question_text') or '')
                reference_answer = question_data.get('answer') or question_data.get('sample_answer') or ''
                
                correctness, feedback, explanation = await evaluate_answer_with_llm(
                    question=question_text,
                    reference_answer=reference_answer,
                    student_answer=student_answer
                )

                # 若題目未包含詳細解析，則使用生成式解析
                if question_data.get('detailed_explanation'):
                    explanation = question_data.get('detailed_explanation')
            
            else:
                # 其他題型 (e.g. true_false or unknown)
                feedback = "(暫不支援此題型評分)"
                correctness = "checked"

            evaluation_results.append({
                "log_id": log_id,
                "question_id": question_id,
                "correctness": correctness,
                "feedback": feedback,
                "explanation": explanation
            })
            
        # 2. 批次更新資料庫
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

    # 3. 回傳結果
    response_results = [
        EvaluationResult(
            log_id=r["log_id"],
            question_id=r["question_id"],
            correctness=r["correctness"],
            feedback=r["feedback"],
            evaluated_at=get_now_taipei().isoformat()
        )
        for r in evaluation_results
    ]
            
    return BatchEvaluateResponse(
        results=response_results,
        summary={}
    )


@router.get(
    "/kps/{kp_id}/logs",
    summary="取得複習作答記錄"
)
async def get_review_logs(
    kp_id: int,
    student_id: int = Depends(get_current_user_id)
):
    """
    取得學生在指定知識點的複習作答記錄
    """
    
    logs = await get_student_logs(
        student_id=student_id,
        knowledge_point_id=kp_id,
        stage="review"
    )
    
    return {
        "knowledge_point_id": kp_id,
        "logs": logs
    }


# ============================================================
# Feature 2: 個人化複習教材（非精熟 KP 的重練題目）
# ============================================================

class PersonalMaterialQuestion(BaseModel):
    question_id: int
    question_text: str
    question_type: str
    source: str  # "retry" | "random"

class PersonalMaterialKP(BaseModel):
    kp_id: int
    kp_name: str
    mastery_level: str
    questions: List[PersonalMaterialQuestion]

class PersonalMaterialsResponse(BaseModel):
    unit_id: int
    kp_materials: List[PersonalMaterialKP]

@router.get(
    "/units/{unit_id}/personal-materials",
    response_model=PersonalMaterialsResponse,
    summary="取得個人化複習練習題（所有非精熟 KP）"
)
async def get_personal_materials(
    unit_id: int,
    count_per_kp: int = Query(2, ge=1, le=5),
    student_id: int = Depends(get_current_user_id)
):
    """
    功能 2：個人化複習教材

    - 找出學生所有非精熟（待加強/尚可）的知識點
    - 優先取預習答錯的 short_answer 題（重複練習）
    - 不足時補充 question_bank 的 short_answer（排除 AI生成 tag）
    """
    kp_materials = await review_service.get_review_personal_materials(
        student_id=student_id,
        unit_id=unit_id,
        count_per_kp=count_per_kp
    )

    return PersonalMaterialsResponse(
        unit_id=unit_id,
        kp_materials=[
            PersonalMaterialKP(
                kp_id=kp["kp_id"],
                kp_name=kp["kp_name"],
                mastery_level=kp["mastery_level"],
                questions=[
                    PersonalMaterialQuestion(**q) for q in kp["questions"]
                ]
            )
            for kp in kp_materials
        ]
    )


# ============================================================
# Feature 3: 精熟 KP AI 推薦挑戰題
# ============================================================

class MasteredChallengeQuestion(BaseModel):
    question_id: int
    kp_id: int
    kp_name: str
    question_text: str
    question_type: str
    difficulty_level: Optional[str] = None
    options: Optional[dict] = None  # MC 選項 {A: '...', B: '...', ...}
    source: str  # "challenge"

class MasteredKpQuestionsResponse(BaseModel):
    unit_id: int
    mastered_kp_questions: List[MasteredChallengeQuestion]
    total_count: int

@router.get(
    "/units/{unit_id}/mastered-kp-questions",
    response_model=MasteredKpQuestionsResponse,
    summary="取得精熟 KP 的 AI 推薦挑戰題"
)
async def get_mastered_kp_questions(
    unit_id: int,
    count_per_kp: int = Query(2, ge=1, le=5),
    student_id: int = Depends(get_current_user_id)
):
    """
    功能 3：精熟知識點 AI 推薦挑戰題

    - 找出學生已精熟的知識點
    - 優先推薦 AI生成 medium/hard 難度題目
    - Fallback：若無 medium/hard，取任意難度 AI生成題
    """
    questions = await review_service.get_mastered_kp_ai_questions(
        student_id=student_id,
        unit_id=unit_id,
        count_per_kp=count_per_kp
    )

    return MasteredKpQuestionsResponse(
        unit_id=unit_id,
        mastered_kp_questions=[MasteredChallengeQuestion(**q) for q in questions],
        total_count=len(questions)
    )


# ============================================================
# Feature: AI 挑戰題繳交 + LLM 評估（純 INSERT 模式）
# 設計原則：評估完成再 INSERT，絕對不使用 UPDATE，不觸發 BERT/LIME
# ============================================================

@router.post(
    "/challenge-logs/submit",
    response_model=SubmitChallengesResponse,
    summary="繳交挑戰題作答並立即 LLM 評估，完整結果 INSERT 至 student_challenge_logs"
)
async def submit_challenges(
    request: SubmitChallengesRequest,
    student_id: int = Depends(get_current_user_id)
):
    """
    接收學生挑戰題的所有作答，進行 LLM 評估，
    再將完整評估結果（含 correctness/feedback/explanation）一次 INSERT 至 student_challenge_logs。

    設計原則：
    - 純 INSERT，絕對不修改舊記錄
    - 重複繳交同一題 = 兩筆独立的記錄
    - 不觸發 BERT/LIME 精熟度評估
    """
    if not request.answers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請至少提供一題作答"
        )

    items = [
        ChallengeAnswerItem(
            question_id=a.question_id,
            knowledge_point_id=a.knowledge_point_id,
            answer=a.answer,
            difficulty_level=a.difficulty_level,
            question_type=a.question_type,
            question_text=a.question_text,
        )
        for a in request.answers
    ]

    results, summary = await submit_and_evaluate_challenges(
        student_id=student_id,
        answers=items,
    )

    return SubmitChallengesResponse(
        results=[ChallengeEvaluationResult(**r) for r in results],
        summary=summary,
    )


class ChallengeHistoryItem(BaseModel):
    """單題歷史作答紀錄"""
    log_id: int
    question_id: int
    answer: str
    correctness: Optional[str] = None
    feedback: Optional[str] = None
    explanation: Optional[str] = None
    answered_at: Optional[str] = None

class ChallengeHistoryResponse(BaseModel):
    """挑戰題歷史查詢回應"""
    history: Dict[int, ChallengeHistoryItem]


@router.post(
    "/challenge-logs/history",
    response_model=Dict[int, ChallengeHistoryItem],
    summary="查詢學生對指定題目最新一次的挑戰紀錄"
)
async def get_challenge_history_api(
    request: dict,
    student_id: int = Depends(get_current_user_id)
):
    """
    查詢指定學生對多題題目的最新一次挑戰紀錄。
    回傳 {question_id: 紀錄資料} 的字典，沒做過的題目不會出現。
    """
    question_ids = request.get("question_ids", [])
    history = get_challenge_history(student_id=student_id, question_ids=question_ids)
    return {str(k): v for k, v in history.items()}
