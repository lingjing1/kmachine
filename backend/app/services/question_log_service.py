"""
Question Log Service

處理學生作答記錄的共用邏輯，供 Preview 和 Review Router 使用。
"""
from typing import List, Dict, Optional, Tuple, Any
import json
from datetime import datetime, timezone
from sqlalchemy import text
from backend.app.utils.time_utils import get_now_taipei
from backend.app.utils.db_logger import engine
from backend.app.services.llm_evaluation_service import (
    evaluate_answer_with_llm, 
    generate_question_explanation
)
from backend.app.services.fill_in_blank_evaluator import evaluate_fill_in_blank


async def create_question_log(
    student_id: int,
    question_id: Optional[int],
    knowledge_point_id: int,
    stage: str,  # 'preview' or 'review'
    answer: str,
    question_type: Optional[str] = None,
    correct_answer: Optional[str] = None,
    question_text: Optional[str] = None,
    detailed_explanation: Optional[str] = None,
    unit_session_id: Optional[Any] = None,
    unit_id: Optional[int] = None,
    course_id: Optional[int] = None
) -> int:
    """
    建立學生作答記錄，支援內嵌題目與詳細解析傳遞
    """
    with engine.connect() as conn:
        # 查詢 unit_id 和 course_id
        effective_unit_id = unit_id
        effective_course_id = course_id
        
        if knowledge_point_id and knowledge_point_id > 0:
            query = text("""
                SELECT unit_id, course_id
                FROM knowledge_points
                WHERE id = :kp_id
            """)
            result = conn.execute(query, {"kp_id": knowledge_point_id}).fetchone()
            if result:
                # 優先使用 KP 原本關聯的 unit/course
                effective_unit_id, effective_course_id = result
        
        # Fallback: if kp_id=0, try to infer from other context if possible, or leave NULL
        # For submission_router, we might want to pass these explicitly if kp is missing
        
        # 插入作答記錄
        # 我們將額外資訊存入 answer jsonb 以支援彈性題型
        answer_data = {
            "text": answer,
            "question_type": question_type,
            "correct_answer": correct_answer,
            "question_text": question_text,
            "detailed_explanation": detailed_explanation
        }

        insert_query = text("""
            INSERT INTO student_question_logs 
            (student_id, question_id, knowledge_point_id, unit_id, course_id, stage, answer, unit_session_id, answered_at)
            VALUES 
            (:student_id, :question_id, :kp_id, :unit_id, :course_id, :stage, CAST(:answer AS jsonb), :sid, :answered_at)
            RETURNING id
        """)
        
        log_id = conn.execute(insert_query, {
            "student_id": student_id,
            "question_id": question_id,
            "kp_id": knowledge_point_id if knowledge_point_id and knowledge_point_id > 0 else None,
            "unit_id": effective_unit_id,
            "course_id": effective_course_id,
            "stage": stage,
            "answer": json.dumps(answer_data, ensure_ascii=False),
            "sid": unit_session_id,
            "answered_at": get_now_taipei()
        }).scalar()
        
        conn.commit()
        
        return log_id


async def batch_evaluate_logs(
    log_ids: List[int],
    student_id: int
) -> Tuple[List[Dict], Dict]:
    """
    批次評估學生作答記錄
    
    Args:
        log_ids: 作答記錄 ID 列表
        student_id: 學生 ID
    
    Returns:
        (results, summary)
        results: 評估結果列表
        summary: 統計摘要
    """
    with engine.connect() as conn:
        # 1. 批次查詢所有作答記錄
        query = text("""
            SELECT 
                sql.id as log_id,
                sql.question_id,
                sql.answer,
                qb.question_data,
                qb.question_type
            FROM student_question_logs sql
            JOIN question_bank qb ON sql.question_id = qb.id
            WHERE sql.id = ANY(:log_ids)
              AND sql.student_id = :student_id
        """)
        
        results = conn.execute(
            query,
            {"log_ids": log_ids, "student_id": student_id}
        ).fetchall()
        
        if not results:
            return [], {"total": 0, "correct": 0, "partially_correct": 0, "incorrect": 0}
        
        # 2. 準備批次評分（呼叫 LLM Service）
        evaluation_results = []
        
        for row in results:
            log_id = row[0]
            question_id = row[1]
            student_answer_data = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            student_answer = student_answer_data.get('text', '')
            
            question_data = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            question_type = row[4]
            question_text = question_data.get('question') or question_data.get('question_text') or ''
            
            # 提取詳細解析與教材脈絡 (優先從題庫取，若無則從作答記錄取)
            detailed_explanation = (
                question_data.get('detailed_explanation') or 
                student_answer_data.get('detailed_explanation')
            )
            source_context = (
                question_data.get('source', {}).get('text') or 
                student_answer_data.get('source_context')
            )
            
            if question_type == 'multiple_choice':
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
                if explanation:
                    feedback += f"\n\n### 題目解析\n{explanation}"
            
            elif question_type == 'true_false':
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
                if explanation:
                    feedback += f"\n\n### 題目解析\n{explanation}"

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
                if explanation:
                    feedback += f"\n\n### 題目解析\n{explanation}"
            
            else:
                # 簡答題或其他使用 LLM 評分
                reference_answer = question_data.get('answer') or question_data.get('sample_answer') or ''
                correctness, feedback, explanation = await evaluate_answer_with_llm(
                    question=question_text,
                    reference_answer=reference_answer,
                    student_answer=student_answer
                )
                if explanation:
                    feedback += f"\n\n### 題目解析\n{explanation}"
            
            evaluation_results.append({
                "log_id": log_id,
                "question_id": question_id,
                "correctness": correctness,
                "feedback": feedback
            })
        
        # 3. 批次更新資料庫
        now = get_now_taipei()
        for result in evaluation_results:
            update_query = text("""
                UPDATE student_question_logs
                SET correctness = :correctness,
                    feedback = :feedback,
                    evaluated_at = :evaluated_at
                WHERE id = :log_id
            """)
            
            conn.execute(update_query, {
                "log_id": result["log_id"],
                "correctness": result["correctness"],
                "feedback": result["feedback"],
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
        
        # 加入 evaluated_at
        for result in evaluation_results:
            result["evaluated_at"] = now.isoformat()
        
        return evaluation_results, summary


async def get_student_logs(
    student_id: int,
    knowledge_point_id: int,
    stage: Optional[str] = None
) -> List[Dict]:
    """
    取得學生的作答記錄
    
    Args:
        student_id: 學生 ID
        knowledge_point_id: 知識點 ID
        stage: 階段過濾 ('preview', 'review', 或 None 取全部)
    
    Returns:
        作答記錄列表
    """
    with engine.connect() as conn:
        if stage:
            query = text("""
                SELECT 
                    sql.id,
                    sql.question_id,
                    sql.answer,
                    sql.correctness,
                    sql.feedback,
                    sql.answered_at,
                    sql.evaluated_at,
                    qb.question_data,
                    kp.name as knowledge_point_name,
                    sql.explanation
                FROM student_question_logs sql
                JOIN question_bank qb ON sql.question_id = qb.id
                LEFT JOIN knowledge_points kp ON sql.knowledge_point_id = kp.id
                WHERE sql.student_id = :student_id
                  AND sql.knowledge_point_id = :kp_id
                  AND sql.stage = :stage
                ORDER BY sql.answered_at DESC
            """)
            results = conn.execute(query, {
                "student_id": student_id,
                "kp_id": knowledge_point_id,
                "stage": stage
            }).fetchall()
        else:
            query = text("""
                SELECT 
                    sql.id,
                    sql.question_id,
                    sql.answer,
                    sql.correctness,
                    sql.feedback,
                    sql.answered_at,
                    sql.evaluated_at,
                    qb.question_data,
                    kp.name as knowledge_point_name,
                    sql.explanation
                FROM student_question_logs sql
                JOIN question_bank qb ON sql.question_id = qb.id
                LEFT JOIN knowledge_points kp ON sql.knowledge_point_id = kp.id
                WHERE sql.student_id = :student_id
                  AND sql.knowledge_point_id = :kp_id
                ORDER BY sql.answered_at DESC
            """)
            results = conn.execute(query, {
                "student_id": student_id,
                "kp_id": knowledge_point_id
            }).fetchall()
        
        logs = []
        for row in results:
            answer_data = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            question_data = json.loads(row[7]) if isinstance(row[7], str) else row[7]
            
            logs.append({
                "log_id": row[0],
                "question_id": row[1],
                "question_text": question_data.get('question') or question_data.get('question_text') or '',
                "student_answer": answer_data.get('text', ''),
                "correctness": row[3],
                "feedback": row[4],
                "answered_at": str(row[5]) if row[5] else None,
                "evaluated_at": str(row[6]) if row[6] else None,
                "explanation": row[9] if row[9] else None,
                "detailed_explanation": row[9] or question_data.get('detailed_explanation') or answer_data.get('detailed_explanation'),
                "knowledge_point_id": knowledge_point_id,
                "knowledge_point_name": row[8] or '',
            })
        
        return logs
