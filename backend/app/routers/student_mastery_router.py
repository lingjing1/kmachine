"""
Student Mastery Router

處理學生精熟度評估相關功能（共用於 Preview 和 Review）：
1. BERT Mastery 評估
2. LIME 可解釋性報告
3. Mastery 狀態查詢
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from pydantic import BaseModel
from typing import List, Optional, Any
import json
import os
import uuid
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei
from sqlalchemy import text

from backend.app.utils.db_logger import engine
from backend.app.services.bert_mastery_service import predict_mastery as bert_predict_mastery
from backend.app.services.lime_explainer_service import explain_mastery
from backend.app.utils.concurrency import run_in_db_pool


router = APIRouter(
    prefix="/api/student/mastery",
    tags=["student-mastery"]
)

# ==================== Helper Functions ====================

# ✅ Phase 3: get_current_user_id 已從 auth_utils 導入，移除本地實作


def _sync_fetch_mastery_context(student_id: int, kp_id: int, stage: str):
    with engine.connect() as conn:
        # 1. 查詢知識點資訊
        kp_info = conn.execute(text("""
            SELECT kp.name as section_name, cu.name as chapter_name
            FROM knowledge_points kp
            JOIN course_units cu ON kp.unit_id = cu.id
            WHERE kp.id = :kp_id
        """), {"kp_id": kp_id}).fetchone()
        
        if not kp_info:
            return None, "找不到知識點"
        
        section_name, chapter_name = kp_info
        
        # 2. 收集簡答題記錄
        logs = conn.execute(text("""
            WITH ranked_logs AS (
                SELECT sql.question_id, sql.answer, sql.correctness, qb.question_data,
                    ROW_NUMBER() OVER (PARTITION BY sql.question_id ORDER BY sql.answered_at DESC) as rn
                FROM student_question_logs sql
                JOIN question_bank qb ON sql.question_id = qb.id
                WHERE sql.student_id = :sid 
                  AND sql.knowledge_point_id = :kid 
                  AND sql.stage = :stage
                  AND qb.question_type = 'short_answer'
                  AND (qb.tags IS NULL OR NOT ('AI生成' = ANY(qb.tags)))
                  -- ↑ 排除 AI生成題：
                  --   Preview mastery: 只用非AI生成的課前練習作答
                  --   Review mastery:  只用課前答錯題（本來就非AI生成）
                  --   精熟KP的AI生成挑戰題作答 不輸入 BERT/LIME
            )
            SELECT answer, correctness, question_data FROM ranked_logs WHERE rn = 1
        """), {"sid": student_id, "kid": kp_id, "stage": stage}).fetchall()
        
        short_answer_parts = []
        correct_stats = {"correct": 0, "partially_correct": 0, "incorrect": 0, "total": len(logs)}
        
        for log in logs:
            q_data = json.loads(log[2]) if isinstance(log[2], str) else log[2]
            q_text = q_data.get('question') or q_data.get('question_text') or ''
            ref_ans = q_data.get('answer') or q_data.get('sample_answer') or ''
            
            ans_data = json.loads(log[0]) if isinstance(log[0], str) else log[0]
            stu_ans = ans_data.get('text', '') if isinstance(ans_data, dict) else str(log[0])
            
            correctness = log[1]
            if correctness in correct_stats:
                correct_stats[correctness] += 1
            
            short_answer_parts.append(f"［題目］：{q_text}\n［參考答案］：{ref_ans}\n［學生答案］：{stu_ans}\n［學生表現］：{correctness}\n")
            
        short_answer_log = "\n".join(short_answer_parts)
        
        return (chapter_name, section_name, short_answer_log, correct_stats), None

async def _fetch_mastery_context(student_id: int, kp_id: int, stage: str):
    """
    獲取 Mastery 評估所需的上下文資料 (用於 BERT/LIME)
    Returns: (chapter_name, section_name, short_answer_log, correct_stats)
    """
    result, error = await run_in_db_pool(_sync_fetch_mastery_context, student_id, kp_id, stage)
    
    if error:
        raise HTTPException(status_code=404, detail=f"找不到知識點 {kp_id}")
        
    return result


# ==================== Pydantic Models ====================

class MasteryEvaluateRequest(BaseModel):
    """Mastery 評估請求"""
    stage: str  # 必填：'preview' 或 'review'
    unit_session_id: Optional[uuid.UUID] = None


class MasteryEvaluateResponse(BaseModel):
    """Mastery 評估回應"""
    knowledge_point_id: int
    knowledge_point_name: str
    mastery_level: str
    confidence_score: float
    evaluated_at: str
    summary: dict


class MasteryExplanationResponse(BaseModel):
    """LIME 解釋回應"""
    knowledge_point_id: int
    knowledge_point_name: str
    mastery_level: str
    html_report: str
    keywords: List[str]
    feature_weights: dict
    created_at: str


# ==================== API Endpoints ====================

@router.post(
    "/kps/{kp_id}/evaluate",
    response_model=MasteryEvaluateResponse,
    summary="評估知識點 Mastery（BERT）"
)
async def evaluate_mastery(
    kp_id: int,
    request: MasteryEvaluateRequest,
    student_id: Optional[int] = Query(None),
    current_user_id: int = Depends(get_current_user_id)
):
    student_id = student_id or current_user_id
    
    # 1. 獲取資料
    chapter, section, log_text, stats = await _fetch_mastery_context(student_id, kp_id, request.stage)
    
    # 如果沒有作答記錄，精熟度應為 "unknown"
    bert_result: dict = {"prediction": "unknown", "prediction_id": None, "confidence": 0.0, "probabilities": {}, "fallback": True, "bert_input": ""}
    if not log_text.strip():
        mastery_level = "unknown"
        confidence = 0.0
    else:
        # 2. BERT 預測
        from backend.app.services.bert_mastery_service import predict_mastery as bert_predict_mastery
        bert_result = await bert_predict_mastery(chapter, section, log_text)
        mastery_level = bert_result["prediction"]
        confidence = bert_result["confidence"]
    
    # 3. LIME 解釋與報告生成
    lime_saved = False
    lime_path = None
    lime_json_data = None
    try:
        from backend.app.services.lime_explainer_service import explain_mastery as lime_explain_mastery
        lime_res = await lime_explain_mastery(chapter, section, log_text)
        
        user_dir = f"user_id_{student_id}"
        # 新路徑：kp_{id}/ 子目錄
        kp_dir = os.path.join("backend", "lime_reports", user_dir, request.stage, f"kp_{kp_id}")
        os.makedirs(kp_dir, exist_ok=True)
        
        # 時間戳 + 掌握度 命名（歷史版本）
        ts = get_now_taipei().strftime("%Y%m%d_%H%M%S")
        ts_suffix = f"{ts}_{mastery_level}"
        
        # 準備 JSON 資料
        raw_ht = lime_res.get('highlighted_text', {})
        # 若 LIME 未填入 original，以 log_text 作為 fallback（確保前端有文字顯示）
        if not isinstance(raw_ht, dict) or not raw_ht.get('original'):
            raw_ht = {"original": log_text, "highlights": []}
        
        lime_json_data = {
            "feature_weights": lime_res.get('feature_weights', []),
            "keywords": lime_res.get('keywords', []),
            "highlighted_text": raw_ht,
            "prediction": lime_res.get('prediction', ''),
            "mastery_level": mastery_level,
            "generated_at": get_now_taipei().isoformat(),
            # ── BERT 輸入 / 輸出記錄 ──
            "bert_input": bert_result.get('bert_input', ''),
            "bert_output": {
                "prediction": bert_result.get('prediction', ''),
                "prediction_id": bert_result.get('prediction_id'),
                "confidence": bert_result.get('confidence'),
                "probabilities": bert_result.get('probabilities', {}),
                "fallback": bert_result.get('fallback', False)
            }
        }
        
        # 歷史版本（帶時間戳）
        hist_json = os.path.join(kp_dir, f"{ts_suffix}.json")
        hist_html = os.path.join(kp_dir, f"{ts_suffix}.html")
        with open(hist_json, 'w', encoding='utf-8') as f:
            json.dump(lime_json_data, f, ensure_ascii=False, indent=2)
        with open(hist_html, 'w', encoding='utf-8') as f:
            f.write(lime_res['html_report'])
        
        # latest（覆寫，供 Dashboard 讀取）
        latest_json = os.path.join(kp_dir, "latest.json")
        latest_html = os.path.join(kp_dir, "latest.html")
        with open(latest_json, 'w', encoding='utf-8') as f:
            json.dump(lime_json_data, f, ensure_ascii=False, indent=2)
        with open(latest_html, 'w', encoding='utf-8') as f:
            f.write(lime_res['html_report'])
            
        lime_saved = True
        # 主表存 latest.html 路徑（Dashboard 顯示用）
        lime_path = f"lime_reports/{user_dir}/{request.stage}/kp_{kp_id}/latest.html"
        # history 表存時間戳路徑（歷史追溯用）
        lime_hist_path = f"lime_reports/{user_dir}/{request.stage}/kp_{kp_id}/{ts_suffix}.html"
    except Exception as e:
        print(f"LIME Error: {e}")
        import traceback
        traceback.print_exc()
        lime_hist_path = None

    # 4. 更新 DB（主表 UPSERT + history INSERT）
    now = get_now_taipei()
    def _sync_update_mastery(sid, kid, level, conf, lime, stg, assessed_at, hist_path, lime_json, correct_stats_data, session_id=None):
        with engine.connect() as conn:
            # ── 主表 UPSERT（先 commit，確保掌握度一定存）──
            conn.execute(text("""
                INSERT INTO student_knowledge_mastery 
                (student_id, course_id, unit_id, knowledge_point_id, mastery_level,
                 preview_mastery_level, preview_confidence, preview_lime_report_path,
                 review_mastery_level, review_confidence, review_lime_report_path,
                 preview_completed, review_completed, last_assessed_at, created_at, updated_at)
                VALUES 
                (:sid, (SELECT course_id FROM knowledge_points WHERE id=:kid), 
                 (SELECT unit_id FROM knowledge_points WHERE id=:kid), :kid, :level,
                 :p_lev, :p_conf, :p_lime, :r_lev, :r_conf, :r_lime,
                 :p_done, :r_done, :now, :now, :now)
                ON CONFLICT (student_id, knowledge_point_id) DO UPDATE SET
                mastery_level = EXCLUDED.mastery_level,
                preview_mastery_level = COALESCE(EXCLUDED.preview_mastery_level, student_knowledge_mastery.preview_mastery_level),
                preview_confidence = COALESCE(EXCLUDED.preview_confidence, student_knowledge_mastery.preview_confidence),
                preview_lime_report_path = COALESCE(EXCLUDED.preview_lime_report_path, student_knowledge_mastery.preview_lime_report_path),
                review_mastery_level = COALESCE(EXCLUDED.review_mastery_level, student_knowledge_mastery.review_mastery_level),
                review_confidence = COALESCE(EXCLUDED.review_confidence, student_knowledge_mastery.review_confidence),
                review_lime_report_path = COALESCE(EXCLUDED.review_lime_report_path, student_knowledge_mastery.review_lime_report_path),
                preview_completed = CASE WHEN :stage='preview' THEN true ELSE student_knowledge_mastery.preview_completed END,
                review_completed = CASE WHEN :stage='review' THEN true ELSE student_knowledge_mastery.review_completed END,
                last_assessed_at = :now, updated_at = :now
            """), {
                "sid": sid, "kid": kid, "level": level,
                "p_lev": level if stg == 'preview' else None,
                "p_conf": conf if stg == 'preview' else None,
                "p_lime": lime if stg == 'preview' else None,
                "r_lev": level if stg == 'review' else None,
                "r_conf": conf if stg == 'review' else None,
                "r_lime": lime if stg == 'review' else None,
                "p_done": stg == 'preview', "r_done": stg == 'review',
                "stage": stg, "now": assessed_at
            })
            conn.commit()  # ← 主表先 commit，保證掌握度存檔
            
            # ── history INSERT（獨立 try/except，失敗不影響主表）──
            try:
                import json as json_mod
                lime_json_str = json_mod.dumps(lime_json, ensure_ascii=False) if lime_json else None
                correct_stats_str = json_mod.dumps(correct_stats_data, ensure_ascii=False)
                conn.execute(text("""
                    INSERT INTO student_knowledge_mastery_history
                    (student_id, knowledge_point_id, stage, mastery_level, confidence,
                     lime_report_path, lime_report_json, correct_stats, assessed_at, created_at)
                    VALUES
                    (:sid, :kid, :stage, :level, :conf,
                     :hist_path,
                     CAST(:lime_json AS jsonb),
                     CAST(:correct_stats AS jsonb),
                     :now, :now)
                """), {
                    "sid": sid, "kid": kid, "stage": stg, "level": level, "conf": conf,
                    "hist_path": hist_path,
                    "lime_json": lime_json_str,
                    "correct_stats": correct_stats_str,
                    "now": assessed_at
                })
                conn.commit()
            except Exception as hist_err:
                print(f"⚠️ History INSERT 失敗（不影響主表）: {hist_err}")
                conn.rollback()

    await run_in_db_pool(
        _sync_update_mastery,
        student_id, kp_id, mastery_level, confidence,
        lime_path, request.stage, now,
        lime_hist_path if lime_saved else None,
        lime_json_data,
        stats,  # correct_stats
        request.unit_session_id
    )

    stats["correct_rate"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
    # stats["has_dialog"] = bool(dialog_text)  # Dialog no longer used
    stats["lime_report_generated"] = lime_saved
    stats["lime_report_path"] = lime_path
    
    return MasteryEvaluateResponse(
        knowledge_point_id=kp_id, knowledge_point_name=section,
        mastery_level=mastery_level, confidence_score=confidence,
        evaluated_at=now.isoformat(), summary=stats
    )


@router.get(
    "/kps/{kp_id}/explain",
    response_model=MasteryExplanationResponse,
    summary="解釋 Mastery 預測結果 (LIME)"
)
async def explain_mastery_endpoint(
    kp_id: int,
    stage: str = "review",
    student_id: Optional[int] = Query(None, description="學生 ID（由 Token 提供，教用可傳入）"),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    使用 LIME 解釋 Mastery 預測
    """
    student_id = student_id or current_user_id
    
    # 1. 獲取資料
    chapter, section, log_text, _ = await _fetch_mastery_context(student_id, kp_id, stage)
    
    # 2. 生成解釋
    from backend.app.services.lime_explainer_service import explain_mastery as lime_explain
    result = await lime_explain(chapter, section, log_text)
    
    return MasteryExplanationResponse(
        knowledge_point_id=kp_id,
        knowledge_point_name=section,
        mastery_level=result["prediction"],
        html_report=result["html_report"],
        keywords=result["keywords"],
        feature_weights=result["feature_weights"],
        created_at=get_now_taipei().isoformat()
    )
