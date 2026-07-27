from sqlalchemy import text
import os
import json
from backend.app.utils.db_logger import engine
from backend.app.schemas.dashboard_schemas import (
    DashboardResponse,
    KnowledgePointStatus,
    StudentAnswer,
)
from backend.app.schemas.lime_schemas import LimeSummary
from backend.app.services.ai_review_service import generate_lime_explanation, generate_unit_review
from backend.app.services.listening_highlights_service import generate_listening_highlights
import json

async def get_dashboard_data(
    course_id: int, 
    unit_id: int, 
    student_id: int, 
    stage: str = 'preview'
) -> DashboardResponse:
    """Aggregate data for the student dashboard.
    Returns a DashboardResponse containing knowledge points, mastery info,
    recent answers, AI review and listening highlights.
    
    Args:
        stage: 'preview' (課前診斷) or 'review' (課後成效)
    """
    # 1️⃣ 取得該單元的 knowledge points 以及 mastery 資料（含 LIME 相關欄位）
    kp_sql = text(
        """
        SELECT kp.id, kp.name, kp.display_order,
               km.preview_completed, km.review_completed,
               km.preview_confidence, km.review_confidence,
               km.preview_lime_report_path, km.review_lime_report_path,
               km.preview_mastery_level, km.review_mastery_level
        FROM knowledge_points kp
        LEFT JOIN student_knowledge_mastery km
          ON km.knowledge_point_id = kp.id
         AND km.student_id = :student_id
         AND km.course_id = :course_id
         AND km.unit_id = :unit_id
        WHERE kp.unit_id = :unit_id
        ORDER BY kp.display_order
        """
    )
    # 2️⃣ 取得最近 3 筆作答（依 knowledge_point 分組，根據 stage 過濾）
    answer_sql = text(
        """
        SELECT ql.knowledge_point_id, ql.question_id,
               ql.answer, ql.answered_at
        FROM student_question_logs ql
        WHERE ql.student_id = :student_id
          AND ql.unit_id = :unit_id
          AND ql.stage = :stage
        ORDER BY ql.answered_at DESC
        """
    )
    
    # 2.5️⃣ 取得單元名稱
    unit_sql = text(
        """
        SELECT name FROM course_units WHERE id = :unit_id
        """
    )
    
    with engine.connect() as conn:
        kp_rows = conn.execute(kp_sql, {
            "student_id": student_id,
            "course_id": course_id,
            "unit_id": unit_id,
        }).fetchall()
        
        answer_rows = conn.execute(answer_sql, {
            "student_id": student_id,
            "unit_id": unit_id,
            "stage": stage,
        }).fetchall()
        
        unit_row = conn.execute(unit_sql, {"unit_id": unit_id}).fetchone()
        unit_name = unit_row[0] if unit_row else f"單元 {unit_id}"

    # 3️⃣ 組裝 recent_answers（只保留每個 knowledge_point 前 3 筆）
    answers_map: dict[int, list[StudentAnswer]] = {}
    for row in answer_rows:
        kp_id = row.knowledge_point_id
        if kp_id not in answers_map:
            answers_map[kp_id] = []
        if len(answers_map[kp_id]) < 3:
            # answer 欄位是 JSONB，裡面通常只有 {"text": "..."}
            try:
                answer_text = json.loads(row.answer).get("text", "")
            except Exception:
                answer_text = str(row.answer)
            answers_map[kp_id].append(
                StudentAnswer(
                    question_id=row.question_id,
                    answer=answer_text,
                    answered_at=row.answered_at,
                )
            )

    # 4️⃣ 組裝 knowledge_points 列表（含 LIME 摘要）
    knowledge_points: list[KnowledgePointStatus] = []
    
    # 準備不同階段的數據供 AI 生成使用
    kp_data_preview = []
    kp_data_review = []
    
    for kp in kp_rows:
        # Default fallback
        mastery_level_generic = "unknown"
        
        # Stage specific mastery levels
        preview_level = kp.preview_mastery_level or mastery_level_generic
        review_level = kp.review_mastery_level or mastery_level_generic
        
        preview_confidence = kp.preview_confidence or 0.0
        review_confidence = kp.review_confidence or 0.0
        
        # 決定卡片上顯示的掌握度（根據選擇的 stage）
        display_mastery_level = preview_level if stage == 'preview' else review_level
        
        # ⚠️ CRITICAL FIX: 如果該知識點完全沒有作答記錄，強行顯示為 unknown (即使 DB 有舊資料或評估偏誤)
        has_answers = len(answers_map.get(kp.id, [])) > 0
        if not has_answers or not display_mastery_level or display_mastery_level == 'unknown':
             display_mastery_level = mastery_level_generic
        
        # 構建 LIME 摘要並讀取診斷關鍵詞
        lime_summary = None
        top_positive_keywords = []
        report_path = kp.preview_lime_report_path if stage == 'preview' else kp.review_lime_report_path
        
        if report_path:
            lime_summary = LimeSummary(
                top_keywords=[], 
                lime_report_url=f"/api/v1/student/dashboard/kps/{kp.id}/lime-report?student_id={student_id}&stage={stage}"
            )
            
            # 嘗試讀取 JSON 以獲集診斷關鍵詞
            json_path = os.path.join("backend", report_path.replace(".html", ".json"))
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        # 新格式: {"feature_weights": [{"keyword": str, "weight": float}, ...]}
                        # 舊格式: {keyword: weight}
                        if "feature_weights" in json_data and isinstance(json_data["feature_weights"], list):
                            # 新格式
                            weights_list = json_data["feature_weights"]
                            positive_weights = [w for w in weights_list if isinstance(w, dict) and w.get("weight", 0) > 0]
                            sorted_weights = sorted(positive_weights, key=lambda x: x.get("weight", 0), reverse=True)
                            top_positive_keywords = [w.get("keyword", "") for w in sorted_weights[:3]]
                        else:
                            # 舊格式 (dict)
                            if isinstance(json_data, dict):
                                sorted_weights = sorted(
                                    [(kw, w) for kw, w in json_data.items() if isinstance(w, (int, float)) and w > 0],
                                    key=lambda x: x[1],
                                    reverse=True
                                )
                                top_positive_keywords = [kw for kw, weight in sorted_weights[:3]]
                except Exception as e:
                    print(f"⚠️  Dashboard: 讀取 LIME JSON 失敗: {e}")
            else:
                # 嘗試檢索是否有對應的 .json 檔案 (預防副檔名不對)
                pass 

        knowledge_points.append(
            KnowledgePointStatus(
                knowledge_point_id=kp.id,
                name=kp.name,
                mastery_level=display_mastery_level, 
                recent_answers=answers_map.get(kp.id, []),
                lime_summary=lime_summary,
            )
        )
        
        # 收集課前預習數據 (包含關鍵詞)
        kp_data_preview.append({
            "name": kp.name,
            "mastery_level": preview_level,
            "confidence": preview_confidence,
            "top_positive": top_positive_keywords if stage == 'preview' else []
        })
        
        # 收集課後複習數據 (包含關鍵詞)
        kp_data_review.append({
            "name": kp.name,
            "mastery_level": review_level,
            "confidence": review_confidence,
            "top_positive": top_positive_keywords if stage == 'review' else []
        })

    # 4.5 如果沒有知識點，初始化空的數據列表
    if not kp_rows:
        kp_data_preview = []
        kp_data_review = []

    # 5️⃣ 取得或生成 AI 回顧與重點（使用 student_unit_reports 作為快取）
    try:
        with engine.connect() as conn:
            # 檢查快取
            report_sql = text("""
                SELECT preview_ai_explain, review_ai_explain,
                       preview_highlights, review_highlights,
                       updated_at
                FROM student_unit_reports
                WHERE student_id = :student_id AND unit_id = :unit_id
            """)
            report_row = conn.execute(report_sql, {
                "student_id": student_id,
                "unit_id": unit_id
            }).fetchone()
            
            use_cache = False
            if report_row:
                 use_cache = True
                 # 1. 檢查基本屬性
                 if stage == 'preview' and not report_row.preview_ai_explain:
                     use_cache = False
                 if stage == 'review' and not report_row.review_ai_explain:
                     use_cache = False
                 
                 # 2. 檢查時效性 (Staleness check)
                 if use_cache:
                     # 檢查是否有更晚的答案紀錄
                     latest_answer = conn.execute(text("""
                        SELECT MAX(answered_at) FROM student_question_logs 
                        WHERE student_id = :sid AND unit_id = :uid AND stage = :stg
                     """), {"sid": student_id, "uid": unit_id, "stg": stage}).scalar()
                     
                     # 檢查是否有更晚的掌握度更新
                     latest_mastery = conn.execute(text("""
                        SELECT MAX(updated_at) FROM student_knowledge_mastery
                        WHERE student_id = :sid AND unit_id = :uid
                     """), {"sid": student_id, "uid": unit_id}).scalar()
                     
                     latest_activity = None
                     if latest_answer and latest_mastery:
                         latest_activity = max(latest_answer, latest_mastery)
                     else:
                         latest_activity = latest_answer or latest_mastery
                         
                     if latest_activity and report_row.updated_at:
                         # Normalize to naive for comparison if needed
                         r_updated = report_row.updated_at.replace(tzinfo=None) if report_row.updated_at.tzinfo else report_row.updated_at
                         l_activity = latest_activity.replace(tzinfo=None) if latest_activity.tzinfo else latest_activity
                         
                         if l_activity > r_updated:
                             print(f"🔄 Cache stale: activity at {l_activity} > report at {r_updated}")
                             use_cache = False
            
            if use_cache and report_row:
                 # 根據 stage 回傳對應欄位
                 ai_review = report_row.preview_ai_explain if stage == 'preview' else report_row.review_ai_explain
                 listening_highlights = report_row.preview_highlights if stage == 'preview' else report_row.review_highlights
                 
                 # 處理空值 (fallback)
                 if not ai_review: ai_review = "尚無回顧"
                 if not listening_highlights: listening_highlights = []
            else:
                 # 生成新資料 - 根據需求生成
                 preview_ai = report_row.preview_ai_explain if report_row else None
                 review_ai = report_row.review_ai_explain if report_row else None
                 preview_hl = report_row.preview_highlights if report_row else None
                 review_hl = report_row.review_highlights if report_row else None
                 
                 # Strict Generation based on Stage
                 if stage == 'preview':
                    if not preview_ai:
                        preview_ai = await generate_unit_review(unit_name, kp_data_preview, stage='preview')
                    if not preview_hl:
                        preview_hl = await generate_listening_highlights(unit_name, kp_data_preview, stage='preview')
                 
                 elif stage == 'review':
                    if not review_ai:
                        review_ai = await generate_unit_review(unit_name, kp_data_review, stage='review')
                    if not review_hl:
                        review_hl = await generate_listening_highlights(unit_name, kp_data_review, stage='review')

                 # 確保當前請求能拿到剛生成的資料 (CRITICAL FIX)
                 ai_review = preview_ai if stage == 'preview' else review_ai
                 listening_highlights = preview_hl if stage == 'preview' else review_hl

                 # 寫入資料庫 (Upsert)
                 upsert_sql = text("""
                    INSERT INTO student_unit_reports 
                    (student_id, course_id, unit_id, 
                     preview_ai_explain, review_ai_explain, 
                     preview_highlights, review_highlights, updated_at)
                    VALUES 
                    (:student_id, :course_id, :unit_id, 
                     :preview_ai, :review_ai, 
                     :preview_hl, :review_hl, NOW())
                    ON CONFLICT (student_id, unit_id) 
                    DO UPDATE SET 
                        preview_ai_explain = EXCLUDED.preview_ai_explain,
                        review_ai_explain = EXCLUDED.review_ai_explain,
                        preview_highlights = EXCLUDED.preview_highlights,
                        review_highlights = EXCLUDED.review_highlights,
                        updated_at = NOW()
                 """)
                 
                 conn.execute(upsert_sql, {
                     "student_id": student_id,
                     "course_id": course_id,
                     "unit_id": unit_id,
                     "preview_ai": preview_ai,
                     "review_ai": review_ai,
                     "preview_hl": json.dumps(preview_hl, ensure_ascii=False) if preview_hl else None,
                     "review_hl": json.dumps(review_hl, ensure_ascii=False) if review_hl else None
                 })
                 conn.commit()
                 
                 # 針對目前儀表板需求回傳
                 ai_review = preview_ai if stage == 'preview' else review_ai
                 listening_highlights = preview_hl if stage == 'preview' else review_hl
                 
                 if not listening_highlights: listening_highlights = []

    except Exception as e:
        print(f"CRITICAL ERROR in Step 5: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to avoid crashing
        ai_review = "系統生成中..."
        listening_highlights = []

    return DashboardResponse(
        course_id=course_id,
        unit_id=unit_id,
        knowledge_points=knowledge_points,
        ai_review=ai_review,
        listening_highlights=listening_highlights,
    )

