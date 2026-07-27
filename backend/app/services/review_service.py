
from typing import List, Dict, Optional, Any
from sqlalchemy import text, func
from backend.app.utils.db_logger import engine
from backend.app.schemas.dashboard_schemas import KnowledgePointStatus
import json
import random


class ReviewService:
    """
    處理課後複習功能的服務：
    1. 班級複習 (弱項分析與內容生成)
    2. 個人複習 (弱項重複測驗)
    """

    async def get_class_weak_points(self, unit_id: int, stage: str) -> List[Dict]:
        """
        找出單元中全班性的弱項知識點。
        優先從 class_statistics 讀取（BERT 或之前保存的數據），若無則進行即時計算。
        
        Args:
            unit_id: 單元 ID
            stage: 階段 - 'preview' (課前) 或 'review' (課後)
        """
        with engine.connect() as conn:
            # 1. 優先從 class_statistics 表讀取已固化的弱項 (BERT 回寫或定時存檔)
            stats_stmt = text("""
                SELECT weak_knowledge_points, total_students 
                FROM class_statistics 
                WHERE unit_id = :unit_id AND stage = :stage
            """)
            stats_row = conn.execute(stats_stmt, {"unit_id": unit_id, "stage": stage}).fetchone()
            
            if stats_row:
                try:
                    raw_weak_points = stats_row.weak_knowledge_points
                    # 某些環境下 SQLAlchemy 會自動解析 JSON 為 list，若非則手動解析
                    if isinstance(raw_weak_points, str):
                        weak_names = json.loads(raw_weak_points)
                    else:
                        weak_names = raw_weak_points
                    
                    if weak_names:
                        # 找出對應的 ID
                        # 在 SQLAlchemy text 中使用 IN :names 並傳入 tuple 是較通用的做法
                        kp_stmt = text("""
                            SELECT id, name FROM knowledge_points 
                            WHERE unit_id = :unit_id AND name IN :names
                        """)
                        kp_rows = conn.execute(kp_stmt, {
                            "unit_id": unit_id, 
                            "names": tuple(weak_names)
                        }).fetchall()
                        kp_map = {r.name: r.id for r in kp_rows}
                        
                        results = []
                        for name in weak_names:
                            results.append({
                                "kp_id": kp_map.get(name),
                                "kp_name": name,
                                "status": "stored_statistics",
                                "student_count": stats_row.total_students or 0
                            })
                        if results:
                            return results
                except Exception as e:
                    pass
            
            # 2. 如果沒有固化數據，則進行即時計算
            # 取得修課學生總數（排除 TA）
            total_stmt = text("""
                SELECT COUNT(*) FROM enrollments e
                JOIN course_units cu ON e.course_id = cu.course_id
                WHERE cu.id = :unit_id AND e.role = 'student'
            """)
            total_students = conn.execute(total_stmt, {"unit_id": unit_id}).scalar() or 0

            if total_students == 0:
                return []

            # 根據階段選擇對應欄位
            mastery_col = "skm.preview_mastery_level" if stage == "preview" else "skm.review_mastery_level"
            
            stmt = text(f"""
                SELECT 
                    kp.id, 
                    kp.name, 
                    COUNT(CASE WHEN {mastery_col} = '精熟' THEN 1 END) as mastered_count,
                    COUNT(CASE WHEN {mastery_col} = '尚可' THEN 1 END) as moderate_count,
                    COUNT(CASE WHEN {mastery_col} = '待加強' THEN 1 END) as explicit_weak_count,
                    COUNT(skm.student_id) as practiced_count
                FROM knowledge_points kp
                LEFT JOIN student_knowledge_mastery skm ON kp.id = skm.knowledge_point_id
                WHERE kp.unit_id = :unit_id
                GROUP BY kp.id, kp.name
                ORDER BY COUNT(CASE WHEN {mastery_col} = '待加強' THEN 1 END) DESC
            """)
            
            rows = conn.execute(stmt, {"unit_id": unit_id}).fetchall()
            
            # 3. Python 側計算：未練習者視為待加強
            results = []
            for row in rows:
                unpracticed = max(0, total_students - row.practiced_count)
                effective_weak = row.explicit_weak_count + unpracticed
                non_weak = row.mastered_count + row.moderate_count

                if effective_weak > non_weak and effective_weak > 0:
                    results.append({
                        "kp_id": row.id,
                        "kp_name": row.name,
                        "weak_count": effective_weak,
                        "student_count": total_students,
                        "status": "majority_weak"
                    })
            
            if results:
                print(f"[ReviewService] 即時計算識別出 {len(results)} 個弱項")
            return results[:5]

    async def get_class_mastery_distribution(self, unit_id: int, stage: str) -> List[Dict]:
        """
        取得單元各知識點的掌握度分佈。
        
        Args:
            unit_id: 單元 ID
            stage: 階段 - 'preview' (課前) 或 'review' (課後)
            
        Return: Dict containing summary and knowledge_points list
        """
        with engine.connect() as conn:
            # 根據階段選擇對應欄位
            mastery_col = "skm.preview_mastery_level" if stage == "preview" else "skm.review_mastery_level"
            
            stmt = text(f"""
                SELECT 
                    kp.id, 
                    kp.name,
                    COUNT(CASE WHEN {mastery_col} = '精熟' THEN 1 END) as mastered_count,
                    COUNT(CASE WHEN {mastery_col} = '尚可' THEN 1 END) as moderate_count,
                    COUNT(CASE WHEN {mastery_col} = '待加強' THEN 1 END) as weak_count,
                    COUNT(skm.student_id) as total_students
                FROM knowledge_points kp
                LEFT JOIN student_knowledge_mastery skm ON kp.id = skm.knowledge_point_id
                WHERE kp.unit_id = :unit_id
                  AND EXISTS (
                      SELECT 1 FROM question_bank qb 
                      WHERE qb.kp_id = kp.id 
                        AND qb.is_deleted IS NOT TRUE 
                        AND qb.is_published IS TRUE
                  )
                GROUP BY kp.id, kp.name
                ORDER BY kp.display_order ASC
            """)
            
            rows = conn.execute(stmt, {"unit_id": unit_id}).fetchall()
            
            # --- 2. 獲取該課程的總修課人數 (Denominator) ---
            # 直接查詢 enrollments 表取得該課程的修課總人數
            
            total_students = 0
            try:
                # 取得 course_id (從 course_units 表)
                c_stmt = text("SELECT course_id FROM course_units WHERE id = :unit_id")
                c_row = conn.execute(c_stmt, {"unit_id": unit_id}).fetchone()
                
                if c_row:
                    course_id = c_row.course_id
                    # 查詢 enrollments
                    e_stmt = text("SELECT COUNT(*) FROM enrollments WHERE course_id = :course_id AND role = 'student'")
                    total_students = conn.execute(e_stmt, {"course_id": course_id}).scalar()
            except Exception as e:
                print(f"Error calculating total students: {e}")
                # Fallback: 使用目前有資料的學生最大數
                total_students = rows[0].total_students if rows else 0
            
            if total_students == 0: 
                 # 避免分母為 0
                total_students = max(1, rows[0].total_students if rows else 1)

            result = {
                "summary": {
                    "total_students": total_students,
                    "preview_completion_rate": 0, # To be calculated
                    "review_completion_rate": 0   # To be calculated
                },
                "knowledge_points": [] 
            }
            
            # --- 3. 計算預習/複習完成率 ---
            # 預習完成定義：有主要概念的 mastery (或 quiz log)
            # 複習完成定義：有 review_mastery
            
            # 簡化計算：
            # 預習完成：該單元所有 KP 中，至少有一個 KP 有 mastery_level 的人數 (或是全部 KP?)
            # 這裡假設：有任何紀錄算已開始。User said "Completion Rate", implying distinct students completed.
            # Let's count distinct students with mastery records for this unit.
            
            p_stmt = text("""
                SELECT COUNT(DISTINCT skm.student_id) 
                FROM student_knowledge_mastery skm
                JOIN knowledge_points kp ON skm.knowledge_point_id = kp.id
                JOIN enrollments e ON skm.student_id = e.user_id 
                    AND e.course_id = (SELECT course_id FROM course_units WHERE id = :unit_id)
                WHERE kp.unit_id = :unit_id 
                  AND skm.preview_mastery_level IS NOT NULL
                  AND e.role = 'student'
            """)
            preview_count = conn.execute(p_stmt, {"unit_id": unit_id}).scalar() or 0
            
            r_stmt = text("""
                SELECT COUNT(DISTINCT skm.student_id) 
                FROM student_knowledge_mastery skm
                JOIN knowledge_points kp ON skm.knowledge_point_id = kp.id
                JOIN enrollments e ON skm.student_id = e.user_id 
                    AND e.course_id = (SELECT course_id FROM course_units WHERE id = :unit_id)
                WHERE kp.unit_id = :unit_id 
                  AND skm.review_mastery_level IS NOT NULL 
                  AND skm.review_completed = true
                  AND e.role = 'student'
            """)
            review_count = conn.execute(r_stmt, {"unit_id": unit_id}).scalar() or 0
            
            result["summary"]["preview_completion_rate"] = round((preview_count / total_students) * 100, 1)
            result["summary"]["review_completion_rate"] = round((review_count / total_students) * 100, 1)
            result["summary"]["preview_count"] = preview_count
            result["summary"]["review_count"] = review_count

            # --- 4. Generate AI Analysis ---
            # Using the raw row data for analysis
            analysis_data = await self._generate_ai_analysis(rows, total_students)
            result["ai_analysis"] = analysis_data



            for row in rows:
                # Normalize to percentage based on ENROLLMENT TOTAL
                # 未練習者也計入「待加強」
                unpracticed = max(0, total_students - row.total_students)
                effective_weak = row.weak_count + unpracticed

                result["knowledge_points"].append({
                    "id": row.id,
                    "name": row.name,
                    "mastered": round((row.mastered_count / total_students) * 100) if total_students else 0,
                    "moderate": round((row.moderate_count / total_students) * 100) if total_students else 0,
                    "weak": round((effective_weak / total_students) * 100) if total_students else 0,
                })

            # --- 5. Persistence: Save class statistics snapshot ---
            try:
                await self.save_class_statistics(unit_id, stage, result)
            except Exception as e:
                print(f"Failed to save class statistics: {e}")
                # Don't block the main flow if persistence fails

            return result

    async def save_class_statistics(self, unit_id: int, stage: str, distribution_data: Dict):
        """
        將掌握度分佈數據持久化至 class_statistics 表。
        採用 3 個精熟等級：mastered, moderate, weak。
        """
        try:
            summary = distribution_data.get("summary", {})
            kps = distribution_data.get("knowledge_points", [])
            
            # 1. 取得 course_id
            with engine.connect() as conn:
                course_row = conn.execute(
                    text("SELECT course_id FROM course_units WHERE id = :unit_id"),
                    {"unit_id": unit_id}
                ).fetchone()
                if not course_row:
                    return
                course_id = course_row.course_id

                # 2. 準備弱項清單 (names only)
                # 直接調用 get_class_weak_points 取得弱項 KP 名稱
                weak_points_data = await self.get_class_weak_points(unit_id, stage)
                weak_kp_names = [wp["kp_name"] for wp in weak_points_data]

                # 3. 準備 3 級掌握度分佈
                final_distribution = []
                for kp in kps:
                    final_distribution.append({
                        "kp_id": kp["id"],
                        "kp_name": kp["name"],
                        "mastered": kp["mastered"],
                        "moderate": kp["moderate"],
                        "weak": kp["weak"]
                    })

                # 4. UPSERT
                stmt = text("""
                    INSERT INTO class_statistics (
                        course_id, unit_id, stage, 
                        weak_knowledge_points, mastery_distribution,
                        total_students, preview_completion_count, review_completion_count
                    )
                    VALUES (
                        :course_id, :unit_id, :stage, 
                        :weak_points, :distribution,
                        :total_students, :preview_count, :review_count
                    )
                    ON CONFLICT (course_id, unit_id, stage) DO UPDATE SET
                        weak_knowledge_points = EXCLUDED.weak_knowledge_points,
                        mastery_distribution = EXCLUDED.mastery_distribution,
                        total_students = EXCLUDED.total_students,
                        preview_completion_count = EXCLUDED.preview_completion_count,
                        review_completion_count = EXCLUDED.review_completion_count,
                        computed_at = NOW()
                """)

                conn.execute(stmt, {
                    "course_id": course_id,
                    "unit_id": unit_id,
                    "stage": stage,
                    "weak_points": json.dumps(weak_kp_names),
                    "distribution": json.dumps(final_distribution),
                    "total_students": summary.get("total_students", 0),
                    "preview_count": summary.get("preview_count", 0),
                    "review_count": summary.get("review_count", 0)
                })
                conn.commit()
                print(f"Successfully saved class statistics for unit {unit_id} ({stage})")
        except Exception as e:
            print(f"Error in save_class_statistics: {e}")
            raise e

    async def get_at_risk_students(self, unit_id: int, stage: str, threshold_count: int = 3, show_all: bool = False) -> List[Dict]:
        """
        找出弱項知識點超過 threshold_count 的學生 (At-risk)。
        
        Args:
            unit_id: 單元 ID
            threshold_count: 弱項數量閾值
            stage: 階段 - 'preview' (課前) 或 'review' (課後)
            show_all: 是否顯示全班學生 (不論是否處於風險中)
        """
        with engine.connect() as conn:
            # 根據階段選擇對應欄位
            mastery_col = "skm.preview_mastery_level" if stage == "preview" else "skm.review_mastery_level"
            
            # 找出待加強的學生，排除 TA
            stmt = text(f"""
                SELECT 
                    u.id as id,
                    u.full_name as name,
                    sp.student_id as real_student_id,
                    COUNT(CASE WHEN {mastery_col} = '待加強' THEN skm.knowledge_point_id END) as weak_point_count,
                    STRING_AGG(CASE WHEN {mastery_col} = '待加強' THEN kp.name END, ',') as weak_kp_names
                FROM users u
                JOIN enrollments e ON u.id = e.user_id
                LEFT JOIN student_profiles sp ON u.id = sp.user_id
                LEFT JOIN student_knowledge_mastery skm ON u.id = skm.student_id
                LEFT JOIN knowledge_points kp ON skm.knowledge_point_id = kp.id AND kp.unit_id = :unit_id
                WHERE e.course_id = (SELECT course_id FROM course_units WHERE id = :unit_id)
                  AND e.role = 'student'
                GROUP BY u.id, u.full_name, sp.student_id
                ORDER BY weak_point_count DESC, u.full_name ASC
            """)
            
            rows = conn.execute(stmt, {"unit_id": unit_id}).fetchall()
            
            results = []
            for row in rows:
                is_at_risk = row.weak_point_count >= threshold_count
                if not show_all and not is_at_risk:
                    continue
                
                results.append({
                    "id": row.id,
                    "name": row.name,
                    "status": "at-risk" if is_at_risk else "normal",
                    "weak_points_count": row.weak_point_count,
                    "student_id": row.real_student_id or f"S{row.id:03d}",
                    "weak_knowledge_points": row.weak_kp_names.split(",") if row.weak_kp_names else []
                })
            
            return results

    async def generate_class_review_content(self, unit_id: int, weak_kp_ids: List[int]) -> Dict:
        """
        根據弱項知識點生成「班級複習內容」。
        目前僅彙整弱項 KP 的重點整理 (Summary)。
        實際實作可能會呼叫 LLM 綜合產出新的摘要。
        """
        content_items = []
        
        with engine.connect() as conn:
            if not weak_kp_ids:
                return {"title": "班級重點複習", "sections": []}

            # 抓取這些知識點現有的 Summary 內容 (從 course_contents)
            stmt = text("""
                SELECT kp.name, cc.content
                FROM knowledge_points kp
                JOIN course_content_knowledge_points cckp ON kp.id = cckp.knowledge_point_id
                JOIN course_contents cc ON cckp.course_content_id = cc.id
                WHERE kp.id IN :kp_ids
                  AND cc.content_subtype IN ('summary', 'preview')
                  AND cc.is_visible = true
                ORDER BY kp.display_order
            """)
            
            rows = conn.execute(stmt, {"kp_ids": tuple(weak_kp_ids)}).fetchall()
            
            for row in rows:
                # Content is commonly stored as JSON string in JSONB column or direct string
                content_text = row.content
                # If content is a JSON string wrapping a string (e.g. '"markdown"'), we might want to unwrap it if needed. 
                # But usually cc.content is the dict or string itself.
                # In migration: content = json.dumps(markdown). So it is a string.
                
                content_items.append({
                    "title": row.name,
                    "content": content_text
                })
        
        return {
            "title": "班級重點複習 (針對弱項)",
            "description": "根據全班答題狀況，系統整理了以下大家較不熟悉的觀念：",
            "sections": content_items
        }

    async def _generate_ai_analysis(self, rows, total_students) -> Dict:
        """
        使用 LLM 生成教學分析與建議。
        """
        if not rows or total_students == 0:
            return {
                "content": "目前數據不足，無法進行分析。",
                "suggestions": []
            }
        
        # 準備統計數據（三級制：精熟、尚可、待加強）
        stats = []
        for row in rows:
            mastered_rate = (row.mastered_count / total_students) * 100
            moderate_rate = (row.moderate_count / total_students) * 100
            weak_rate = (row.weak_count / total_students) * 100
            stats.append({
                "name": row.name,
                "mastered_rate": round(mastered_rate, 1),
                "moderate_rate": round(moderate_rate, 1),
                "weak_rate": round(weak_rate, 1)
            })
        
        # 找出最佳與最弱的知識點
        best_kp = stats[0]
        worst_kp = stats[0]
        
        for s in stats:
            if s['mastered_rate'] > best_kp['mastered_rate']:
                best_kp = s
            if s['weak_rate'] > worst_kp['weak_rate']:
                worst_kp = s
        
        # 嘗試呼叫 LLM
        try:
            from openai import OpenAI
            from backend.app.config.settings import settings
            
            if not settings.openai_api_key:
                raise ValueError("No OpenAI API key")
            
            client = OpenAI(api_key=settings.openai_api_key)
            
            # 建構 prompt
            stats_text = "\n".join([
                f"- {s['name']}: 精熟率 {s['mastered_rate']}%, 尚可率 {s['moderate_rate']}%, 待加強率 {s['weak_rate']}%"
                for s in stats
            ])
            
            prompt = f"""你是一位教學分析助理。根據以下班級知識點掌握度統計，請提供教學分析與建議。

## 統計數據
總學生數: {total_students} 人

{stats_text}

## 任務
1. 用一段簡短的繁體中文描述班級整體學習狀況（2-3句話）
2. 針對弱項知識點提供 2-3 條具體的教學建議

請以 JSON 格式回覆：
{{"content": "學習狀況描述", "suggestions": ["建議1", "建議2", "建議3"]}}
"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是教學分析助理，專門協助教師改進教學。請用繁體中文回覆。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "content": result.get("content", ""),
                "suggestions": result.get("suggestions", [])
            }
            
        except Exception as e:
            print(f"⚠️ LLM 分析失敗，使用 fallback: {e}")
            
            # Fallback: 使用模板
            content = f"全班對於「{best_kp['name']}」掌握良好（{int(best_kp['mastered_rate'])}% 精熟）。"
            
            suggestions = []
            if worst_kp['weak_rate'] > 0:
                content += f" 然而，「{worst_kp['name']}」知識點有 {int(worst_kp['weak_rate'])}% 學生仍需加強。"
                suggestions.append(f"建議針對「{worst_kp['name']}」補充更多案例說明。")
            
            return {
                "content": content,
                "suggestions": suggestions
            }

    async def get_review_personal_materials(
        self,
        student_id: int,
        unit_id: int,
        count_per_kp: int = 2
    ) -> List[Dict]:
        """
        功能 2：個人化複習教材
        針對學生所有非精熟(待加強/尚可/unknown)的知識點，
        優先抓取預習階段答錯的簡答題，不足則從題庫補充 short_answer（排除 AI生成）。
        unknown = 尚未預習過，直接走隨機補題 fallback。
        """
        kp_materials = []

        with engine.connect() as conn:
            # 1. 找出該單元所有非精熟的 KP（含 unknown = 尚未預習）
            stmt = text("""
                SELECT kp.id, kp.name,
                       COALESCE(skm.review_mastery_level, skm.mastery_level, '待加強') as mastery_level
                FROM knowledge_points kp
                LEFT JOIN student_knowledge_mastery skm ON (
                    kp.id = skm.knowledge_point_id AND skm.student_id = :sid
                )
                WHERE kp.unit_id = :uid
                  AND COALESCE(skm.review_mastery_level, skm.mastery_level, '待加強') IN ('待加強', '尚可', 'unknown')
                ORDER BY kp.display_order
            """)
            kp_rows = conn.execute(stmt, {"sid": student_id, "uid": unit_id}).fetchall()

            for kp_row in kp_rows:
                kp_id = kp_row[0]
                kp_name = kp_row[1]
                mastery_level = kp_row[2]

                questions = []

                # 2a. 優先：預習階段答錯的簡答題
                wrong_stmt = text("""
                    SELECT DISTINCT ON (sql.question_id)
                           qb.id, qb.question_data, qb.question_type
                    FROM student_question_logs sql
                    JOIN question_bank qb ON sql.question_id = qb.id
                    WHERE sql.student_id = :sid
                      AND sql.knowledge_point_id = :kpid
                      AND sql.stage = 'preview'
                      AND sql.correctness IN ('incorrect', 'partially_correct')
                      AND qb.question_type = 'short_answer'
                    ORDER BY sql.question_id, sql.answered_at DESC
                    LIMIT :lmt
                """)
                wrong_rows = conn.execute(wrong_stmt, {
                    "sid": student_id, "kpid": kp_id, "lmt": count_per_kp
                }).fetchall()

                answered_ids = []
                for row in wrong_rows:
                    q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    questions.append({
                        "question_id": row[0],
                        "question_text": q_data.get("question") or q_data.get("question_text", ""),
                        "question_type": row[2],
                        "source": "retry"
                    })
                    answered_ids.append(row[0])

                # 2b. Fallback：從題庫補充 short_answer（排除 AI生成）
                remaining = count_per_kp - len(questions)
                if remaining > 0:
                    exclude_ids = answered_ids if answered_ids else [-1]
                    fill_stmt = text("""
                        SELECT qb.id, qb.question_data, qb.question_type
                        FROM question_bank qb
                        WHERE qb.kp_id = :kpid
                          AND qb.question_type = 'short_answer'
                          AND qb.is_published = true
                          AND qb.is_deleted IS NOT TRUE
                          AND NOT (qb.tags @> ARRAY['AI生成']::text[])
                          AND qb.id NOT IN :excl
                        ORDER BY RANDOM()
                        LIMIT :lmt
                    """)
                    fill_rows = conn.execute(fill_stmt, {
                        "kpid": kp_id,
                        "excl": tuple(exclude_ids),
                        "lmt": remaining
                    }).fetchall()
                    for row in fill_rows:
                        q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                        questions.append({
                            "question_id": row[0],
                            "question_text": q_data.get("question") or q_data.get("question_text", ""),
                            "question_type": row[2],
                            "source": "random"
                        })

                if questions:
                    kp_materials.append({
                        "kp_id": kp_id,
                        "kp_name": kp_name,
                        "mastery_level": mastery_level,
                        "questions": questions
                    })

        return kp_materials

    async def get_mastered_kp_ai_questions(
        self,
        student_id: int,
        unit_id: int,
        count_per_kp: int = 2
    ) -> List[Dict]:
        """
        功能 3：精熟/unknown 知識點 AI 推薦題
        - 精熟 KP：優先 medium/hard AI生成題，fallback 任意難度
        - unknown KP（尚未預習）：同上策略，作為首次接觸推薦
        """
        all_questions = []

        with engine.connect() as conn:
            # 1. 找出精熟 或 unknown 的 KP（LEFT JOIN 以涵蓋無 mastery 記錄的情況）
            stmt = text("""
                SELECT kp.id, kp.name,
                       COALESCE(skm.review_mastery_level, skm.mastery_level, 'unknown') as mastery_level
                FROM knowledge_points kp
                LEFT JOIN student_knowledge_mastery skm ON (
                    kp.id = skm.knowledge_point_id AND skm.student_id = :sid
                )
                WHERE kp.unit_id = :uid
                  AND COALESCE(skm.review_mastery_level, skm.mastery_level, 'unknown') IN ('精熟', 'unknown')
                ORDER BY kp.display_order
            """)
            kp_rows = conn.execute(stmt, {"sid": student_id, "uid": unit_id}).fetchall()

            for kp_row in kp_rows:
                kp_id = kp_row[0]
                kp_name = kp_row[1]

                # 2. 抓取 AI生成 medium/hard 題（已答過的除外）
                ai_stmt = text("""
                    SELECT qb.id, qb.question_data, qb.question_type, qb.difficulty_level
                    FROM question_bank qb
                    WHERE qb.kp_id = :kpid
                      AND qb.is_published = true
                      AND qb.is_deleted IS NOT TRUE
                      AND qb.tags @> ARRAY['AI生成']::text[]
                      AND qb.difficulty_level IN ('medium', 'hard')
                      AND qb.id NOT IN (
                          SELECT question_id FROM student_question_logs
                          WHERE student_id = :sid AND knowledge_point_id = :kpid
                            AND question_id IS NOT NULL
                      )
                    ORDER BY RANDOM()
                    LIMIT :lmt
                """)
                rows = conn.execute(ai_stmt, {
                    "sid": student_id, "kpid": kp_id, "lmt": count_per_kp
                }).fetchall()

                # 3. Fallback：任意難度的 AI生成題
                if not rows:
                    fallback_stmt = text("""
                        SELECT qb.id, qb.question_data, qb.question_type, qb.difficulty_level
                        FROM question_bank qb
                        WHERE qb.kp_id = :kpid
                          AND qb.is_published = true
                          AND qb.is_deleted IS NOT TRUE
                          AND qb.tags @> ARRAY['AI生成']::text[]
                          AND qb.id NOT IN (
                              SELECT question_id FROM student_question_logs
                              WHERE student_id = :sid AND knowledge_point_id = :kpid
                                AND question_id IS NOT NULL
                          )
                        ORDER BY RANDOM()
                        LIMIT :lmt
                    """)
                    rows = conn.execute(fallback_stmt, {
                        "sid": student_id, "kpid": kp_id, "lmt": count_per_kp
                    }).fetchall()

                for row in rows:
                    q_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    all_questions.append({
                        "question_id": row[0],
                        "kp_id": kp_id,
                        "kp_name": kp_name,
                        "question_text": q_data.get("question") or q_data.get("question_text", ""),
                        "question_type": row[2],
                        "difficulty_level": row[3],
                        "options": q_data.get("options", {}),
                        "source": "challenge"
                    })

        return all_questions


review_service = ReviewService()
