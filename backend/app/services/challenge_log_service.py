"""
Challenge Log Service

處理精熟挑戰題作答記錄的邏輯，存入 student_challenge_logs 資料表。

設計原則：
- 每次繳交 = 一次 LLM 評估 + 一筆 INSERT（含完整評估結果）
- 絕對不使用 UPDATE，保留完整歷史記錄
- 不觸發 BERT/LIME 精熟度評估
"""
from typing import List, Dict, Optional, Tuple
import json
from datetime import datetime, timezone
from sqlalchemy import text
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine
from backend.app.services.llm_evaluation_service import (
    evaluate_answer_with_llm,
    generate_question_explanation,
)
from backend.app.services.fill_in_blank_evaluator import evaluate_fill_in_blank


# ---- Request / Result types (internal) --------------------------------

class ChallengeAnswerItem:
    """單題挑戰作答（傳入 submit_and_evaluate_challenges 的單筆資料）"""
    def __init__(
        self,
        question_id: int,
        knowledge_point_id: int,
        answer: str,
        difficulty_level: Optional[str] = None,
        question_type: Optional[str] = None,
        question_text: Optional[str] = None,
    ):
        self.question_id = question_id
        self.knowledge_point_id = knowledge_point_id
        self.answer = answer
        self.difficulty_level = difficulty_level
        self.question_type = question_type
        self.question_text = question_text


# ---- Core helper: look up metadata for an answer ----------------------

def _get_kp_meta(conn, knowledge_point_id: int) -> Tuple[int, int]:
    """取得知識點對應的 unit_id 與 course_id"""
    row = conn.execute(
        text("SELECT unit_id, course_id FROM knowledge_points WHERE id = :kp_id"),
        {"kp_id": knowledge_point_id},
    ).fetchone()
    if not row:
        raise ValueError(f"找不到知識點 {knowledge_point_id}")
    return row[0], row[1]


def _get_question_data(conn, question_id: int) -> Dict:
    """從 question_bank 取得題目資料"""
    row = conn.execute(
        text("SELECT question_data, question_type FROM question_bank WHERE id = :qid"),
        {"qid": question_id},
    ).fetchone()
    if not row:
        return {}
    qd = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
    qd["_question_type"] = row[1]
    return qd


# ---- LLM Evaluation helper --------------------------------------------

async def _evaluate_single(
    student_answer: str,
    question_data: Dict,
    fallback_question_text: Optional[str],
) -> Tuple[str, str, Optional[str]]:
    """
    對單題進行 LLM 評估，回傳 (correctness, feedback, explanation)
    """
    question_type = question_data.get("_question_type", "short_answer")
    question_text = (
        question_data.get("question")
        or question_data.get("question_text")
        or fallback_question_text
        or ""
    )
    detailed_explanation: Optional[str] = question_data.get("detailed_explanation")
    source_context: Optional[str] = question_data.get("source", {}).get("text")
    explanation: Optional[str] = None

    if question_type == "multiple_choice":
        correct_answer = question_data.get("correct_answer", "")
        if student_answer and correct_answer and student_answer.strip().upper() == correct_answer.strip().upper():
            correctness, feedback = "correct", "答案正確！"
        else:
            correctness, feedback = "incorrect", f"答案錯誤。正確答案是 {correct_answer}。"

        explanation = detailed_explanation or await generate_question_explanation(
            question=question_text,
            correct_answer=correct_answer,
            student_answer=student_answer,
            question_type=question_type,
            options=question_data.get("options"),
            context=source_context,
        )
        if explanation:
            feedback += f"\n\n### 題目解析\n{explanation}"

    elif question_type == "true_false":
        correct_answer = question_data.get("correct_answer", "")
        if student_answer and correct_answer and student_answer.strip().lower() == correct_answer.strip().lower():
            correctness, feedback = "correct", "答案正確！"
        else:
            correctness, feedback = "incorrect", f"答案錯誤。正確答案是 {correct_answer}。"

        explanation = detailed_explanation or await generate_question_explanation(
            question=question_text,
            correct_answer=correct_answer,
            student_answer=student_answer,
            question_type=question_type,
            context=source_context,
        )
        if explanation:
            feedback += f"\n\n### 題目解析\n{explanation}"

    elif question_type == "fill_in_blank":
        # 填空題：智慧比對（正規化 + 模糊匹配）
        correct_answer = question_data.get("correct_answer", "")
        correctness, feedback = evaluate_fill_in_blank(student_answer, correct_answer)

        explanation = detailed_explanation or await generate_question_explanation(
            question=question_text,
            correct_answer=correct_answer,
            student_answer=student_answer,
            question_type=question_type,
            context=source_context,
        )
        if explanation:
            feedback += f"\n\n### 題目解析\n{explanation}"

    else:
        # 簡答題：使用 LLM 評分
        reference_answer = question_data.get("answer") or question_data.get("sample_answer") or ""
        correctness, feedback, explanation = await evaluate_answer_with_llm(
            question=question_text,
            reference_answer=reference_answer,
            student_answer=student_answer,
        )
        if explanation:
            feedback += f"\n\n### 題目解析\n{explanation}"

    return correctness, feedback, explanation


# ---- Public API -------------------------------------------------------

async def submit_and_evaluate_challenges(
    student_id: int,
    answers: List[ChallengeAnswerItem],
) -> Tuple[List[Dict], Dict]:
    """
    提交精熟挑戰題作答並進行 LLM 評估，最後一次性 INSERT 完整記錄。

    設計原則：
    - LLM 先評估所有答案
    - 評估完成後才批次 INSERT（含 correctness / feedback / explanation）
    - 完全不使用 UPDATE，保留完整歷史紀錄
    - 不觸發 BERT/LIME 精熟度評估

    Returns:
        (results, summary)
        results: [{log_id, question_id, correctness, feedback, explanation, evaluated_at}]
        summary: {total, correct, partially_correct, incorrect}
    """
    now = get_now_taipei()
    evaluated: List[Dict] = []

    # Phase 1: 從 DB 取得題目資料
    with engine.connect() as conn:
        question_data_map: Dict[int, Dict] = {}
        kp_meta_map: Dict[int, Tuple[int, int]] = {}

        for item in answers:
            if item.question_id not in question_data_map:
                question_data_map[item.question_id] = _get_question_data(conn, item.question_id)
            if item.knowledge_point_id not in kp_meta_map:
                kp_meta_map[item.knowledge_point_id] = _get_kp_meta(conn, item.knowledge_point_id)

    # Phase 2: LLM 評估（在 DB session 外執行，避免長時間持鎖）
    for item in answers:
        qd = question_data_map.get(item.question_id, {})
        correctness, feedback, explanation = await _evaluate_single(
            student_answer=item.answer,
            question_data=qd,
            fallback_question_text=item.question_text,
        )
        evaluated.append({
            "item": item,
            "correctness": correctness,
            "feedback": feedback,
            "explanation": explanation,
        })

    # Phase 3: 批次 INSERT（含完整評估結果）
    results: List[Dict] = []
    with engine.connect() as conn:
        for ev in evaluated:
            item: ChallengeAnswerItem = ev["item"]
            unit_id, course_id = kp_meta_map[item.knowledge_point_id]

            answer_data = {
                "text": item.answer,
                "question_type": item.question_type,
                "question_text": item.question_text,
            }

            log_id = conn.execute(
                text("""
                    INSERT INTO student_challenge_logs
                    (student_id, question_id, knowledge_point_id, unit_id, course_id,
                     difficulty_level, answer, correctness, feedback, explanation,
                     answered_at, evaluated_at)
                    VALUES
                    (:student_id, :question_id, :kp_id, :unit_id, :course_id,
                     :difficulty_level, CAST(:answer AS jsonb),
                     :correctness, :feedback, :explanation,
                     :answered_at, :evaluated_at)
                    RETURNING id
                """),
                {
                    "student_id":       student_id,
                    "question_id":      item.question_id,
                    "kp_id":            item.knowledge_point_id,
                    "unit_id":          unit_id,
                    "course_id":        course_id,
                    "difficulty_level": item.difficulty_level,
                    "answer":           json.dumps(answer_data, ensure_ascii=False),
                    "correctness":      ev["correctness"],
                    "feedback":         ev["feedback"],
                    "explanation":      ev["explanation"],
                    "answered_at":      now,
                    "evaluated_at":     now,
                }
            ).scalar()

            results.append({
                "log_id":       log_id,
                "question_id":  item.question_id,
                "correctness":  ev["correctness"],
                "feedback":     ev["feedback"],
                "explanation":  ev["explanation"],
                "evaluated_at": now.isoformat(),
            })

        conn.commit()

    summary = {
        "total":             len(results),
        "correct":           sum(1 for r in results if r["correctness"] == "correct"),
        "partially_correct": sum(1 for r in results if r["correctness"] == "partially_correct"),
        "incorrect":         sum(1 for r in results if r["correctness"] == "incorrect"),
    }

    return results, summary


# ---- History queries --------------------------------------------------

def get_challenge_history(
    student_id: int,
    question_ids: List[int],
) -> Dict[int, Dict]:
    """
    查詢指定學生對指定題目最近一次的挑戰紀錄。

    Returns:
        {question_id: {log_id, answer, correctness, feedback, explanation, answered_at}}
        只有做過的題目才會出現在結果中。
    """
    if not question_ids:
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT ON (question_id)
                    id, question_id, answer, correctness, feedback, explanation, answered_at
                FROM student_challenge_logs
                WHERE student_id = :student_id
                  AND question_id = ANY(:question_ids)
                ORDER BY question_id, answered_at DESC
            """),
            {"student_id": student_id, "question_ids": question_ids},
        ).fetchall()

    result: Dict[int, Dict] = {}
    for row in rows:
        log_id, question_id, answer_data, correctness, feedback, explanation, answered_at = row
        # answer 欄位是 jsonb，取出 text 欄位
        student_answer = ""
        if isinstance(answer_data, dict):
            student_answer = answer_data.get("text", "")
        elif isinstance(answer_data, str):
            try:
                student_answer = json.loads(answer_data).get("text", "")
            except Exception:
                student_answer = answer_data

        result[question_id] = {
            "log_id":        log_id,
            "question_id":   question_id,
            "answer":        student_answer,
            "correctness":   correctness,
            "feedback":      feedback,
            "explanation":   explanation,
            "answered_at":   answered_at.isoformat() if answered_at else None,
        }

    return result
