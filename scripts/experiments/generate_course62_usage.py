"""
Course 62「人工智慧教育應用概論」學生使用量統計腳本（一次性任務）

輸出三個 CSV 到同資料夾：
  1. course_62_unit_metric_stats.csv    (每單元各指標統計值與 P75 anchor)
  2. course_62_student_unit_detail.csv  (long, 24 學生 × 5 單元 = 120 列，已排除 u1)
  3. course_62_student_summary.csv      (wide, 24 學生 × 1 列，44 欄，含使用量分級)

計分規則（最終版）：
  單元分數 = (①閱讀生成教材 + ②閱讀附件 + ③作答綜合 + ④AI對話) / 有效項目數
  ①②④ 用該單元全班 P75 當 anchor：score = min(值/P75, 1.0) × 10
      若 P75 ≤ 0（全班至少 75% 為 0）→ 該項剔除分母
      若該單元無此類內容（如無附件/無教材）→ 該項剔除分母
  ③ = (參與度 × 0.6 + 正確率 × 0.4) × 10
      參與度 = (有作答課前? 1 : 0) + (有作答課後 OR 挑戰? 1 : 0)，/ 2
      正確率 = Σ correctness / 分母
        課前/課後：correct=1, partially_correct=0.5, incorrect/null=0；全納分母
        挑戰：correct 才納入分子與分母；其餘忽略
  學期平均 = (u2..u6 分數) / 5   # u1 (課堂簡介) 不計入任何 CSV

使用量分級 (1-10 整數)：
  以全班學期平均分的 P75 當 anchor，公式：
    grade = round_half_up(min(學期平均 / P75, 1.0) * 9 + 1)
  範圍 1~10；沒用系統者仍為 1（下限）。
"""
import csv
import math
import os
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text

from backend.app.config.settings import settings

COURSE_ID = 62
EXCLUDED_USER_IDS = (7, 37)  # test, 學生魚
EXCLUDED_TOPIC_IDS = (1,)    # u1 課堂簡介
OUTPUT_DIR = REPO_ROOT / "docs" / "statics" / "studentUsage"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def percentile(values, p):
    """Linear-interpolation percentile (matches numpy default)."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    idx = (n - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def anchor_score(value, anchor):
    """P75 anchor-based score: min(value / anchor, 1.0) × 10.
    Returns None if anchor <= 0 (signals drop from denominator)."""
    if anchor is None or anchor <= 0:
        return None
    return min(value / anchor, 1.0) * 10


def round_half_up(x):
    """傳統四捨五入（Python 的 round 採用銀行家捨入，半值時偏向偶數）。"""
    return int(math.floor(x + 0.5))


def usage_grade(sem_avg, p75):
    """學期平均分 → 1-10 整數使用量分級。
    公式：round(min(avg / P75, 1.0) * 9 + 1)，範圍 [1, 10]。"""
    if p75 is None or p75 <= 0:
        return 1 if sem_avg <= 0 else 10
    ratio = min(sem_avg / p75, 1.0)
    return round_half_up(ratio * 9 + 1)


def get_engine():
    dsn = re.sub(r"^postgresql\+psycopg2://", "postgresql://", settings.database_url)
    return create_engine(dsn)


def fetch_units(conn):
    rows = conn.execute(text("""
        SELECT id AS unit_id, topic_id, name
        FROM course_units
        WHERE course_id = :cid
        ORDER BY topic_id, id
    """), {"cid": COURSE_ID}).all()
    return [dict(r._mapping) for r in rows]


def fetch_students(conn):
    rows = conn.execute(text("""
        SELECT u.id AS user_id, u.full_name, sp.student_id
        FROM enrollments en
        JOIN users u ON u.id = en.user_id
        LEFT JOIN student_profiles sp ON sp.user_id = u.id
        WHERE en.course_id = :cid AND en.role = 'student'
          AND u.id NOT IN :excluded
        ORDER BY sp.student_id NULLS LAST, u.id
    """), {"cid": COURSE_ID, "excluded": EXCLUDED_USER_IDS}).all()
    return [dict(r._mapping) for r in rows]


def fetch_unit_material_ids(conn, unit_id):
    """該單元 visible 的生成教材 id 集合。"""
    rows = conn.execute(text("""
        SELECT id FROM course_contents
        WHERE course_id = :cid AND unit_id = :uid
          AND is_visible = true AND content_type = 'material'
    """), {"cid": COURSE_ID, "uid": unit_id}).all()
    return [r[0] for r in rows]


def fetch_unit_attachment_ids(conn, unit_id):
    """該單元的附件 id 集合 (attachable_type='unit')。"""
    rows = conn.execute(text("""
        SELECT id FROM attachments
        WHERE attachable_type = 'unit' AND attachable_id = :uid
    """), {"uid": unit_id}).all()
    return [r[0] for r in rows]


def correctness_score(value):
    if value == "correct":
        return 1.0
    if value == "partially_correct":
        return 0.5
    return 0.0


def compute_student_unit_raw(conn, user_id, unit_id, material_ids, attachment_ids):
    """計算該學生 × 該單元的原始指標與正確率。"""
    # ① 閱讀生成教材分鐘
    if material_ids:
        sec = conn.execute(text("""
            SELECT COALESCE(SUM(stay_duration_seconds), 0)
            FROM material_reading_logs
            WHERE user_id = :uid AND unit_id = :unit AND content_id IN :mids
        """), {"uid": user_id, "unit": unit_id, "mids": tuple(material_ids)}).scalar() or 0
    else:
        sec = 0
    read_material_min = round(sec / 60.0, 1)

    # ② 閱讀附件分鐘
    if attachment_ids:
        sec = conn.execute(text("""
            SELECT COALESCE(SUM(reading_time_seconds), 0)
            FROM attachment_reading_logs
            WHERE student_id = :uid AND attachment_id IN :aids
        """), {"uid": user_id, "aids": tuple(attachment_ids)}).scalar() or 0
    else:
        sec = 0
    read_attach_min = round(sec / 60.0, 1)

    # ③ 作答 — 課前（每題取最佳一次）
    pre_rows = conn.execute(text("""
        SELECT question_id, MAX(CASE correctness
                WHEN 'correct' THEN 1.0
                WHEN 'partially_correct' THEN 0.5
                ELSE 0.0 END) AS best_score
        FROM student_question_logs
        WHERE student_id = :uid AND unit_id = :unit AND stage = 'preview'
        GROUP BY question_id
    """), {"uid": user_id, "unit": unit_id}).all()
    pre_count = len(pre_rows)
    pre_score_sum = sum(float(r[1]) for r in pre_rows)

    # 課後
    post_rows = conn.execute(text("""
        SELECT question_id, MAX(CASE correctness
                WHEN 'correct' THEN 1.0
                WHEN 'partially_correct' THEN 0.5
                ELSE 0.0 END) AS best_score
        FROM student_question_logs
        WHERE student_id = :uid AND unit_id = :unit AND stage = 'review'
        GROUP BY question_id
    """), {"uid": user_id, "unit": unit_id}).all()
    post_count = len(post_rows)
    post_score_sum = sum(float(r[1]) for r in post_rows)

    # 挑戰（每題最佳一次；只有 correct 納入分子與分母）
    chal_rows = conn.execute(text("""
        SELECT question_id, MAX(CASE correctness WHEN 'correct' THEN 1 ELSE 0 END) AS any_correct,
               COUNT(*) AS attempts
        FROM student_challenge_logs
        WHERE student_id = :uid AND unit_id = :unit
        GROUP BY question_id
    """), {"uid": user_id, "unit": unit_id}).all()
    chal_attempt_count = len(chal_rows)  # 展示欄用
    chal_correct_count = sum(1 for r in chal_rows if r[1] == 1)

    # 正確率
    numerator = pre_score_sum + post_score_sum + chal_correct_count
    denominator = pre_count + post_count + chal_correct_count
    correctness = (numerator / denominator) if denominator > 0 else 0.0

    # 參與度
    pre_part = 1 if pre_count > 0 else 0
    post_part = 1 if (post_count > 0 or chal_attempt_count > 0) else 0
    participation = (pre_part + post_part) / 2.0

    # ③ 作答綜合分
    answer_score = (participation * 0.6 + correctness * 0.4) * 10

    # ④ AI 對話輪次
    turns = conn.execute(text("""
        SELECT COUNT(*) FROM student_chatbot_turn_logs
        WHERE student_id = :uid AND unit_id = :unit AND course_id = :cid
    """), {"uid": user_id, "unit": unit_id, "cid": COURSE_ID}).scalar() or 0

    return {
        "read_material_min": read_material_min,
        "read_attach_min": read_attach_min,
        "pre_count": pre_count,
        "post_count": post_count,
        "chal_count": chal_attempt_count,
        "ai_turns": int(turns),
        "correctness": round(correctness, 3),
        "answer_score": round(answer_score, 2),
        "pre_part": pre_part,
        "post_part": post_part,
    }


def compute_unit_distribution(students_rows, unit_raw_by_student):
    """計算該單元 3 指標的分佈統計與 P75 anchor。"""
    mat_vals = [unit_raw_by_student[s["user_id"]]["read_material_min"] for s in students_rows]
    att_vals = [unit_raw_by_student[s["user_id"]]["read_attach_min"] for s in students_rows]
    ai_vals = [unit_raw_by_student[s["user_id"]]["ai_turns"] for s in students_rows]

    def summarize(vals):
        return {
            "n_zero": sum(1 for v in vals if v == 0),
            "median": round(statistics.median(vals), 2) if vals else 0.0,
            "mean": round(statistics.mean(vals), 2) if vals else 0.0,
            "p75": round(percentile(vals, 75), 2),
            "p90": round(percentile(vals, 90), 2),
            "max": round(max(vals), 2) if vals else 0.0,
        }

    return {
        "material": summarize(mat_vals),
        "attachment": summarize(att_vals),
        "ai": summarize(ai_vals),
    }


def compute_unit_scores(students_rows, unit_raw_by_student, unit_dist,
                        unit_has_material, unit_has_attachment):
    """一個單元內，用 P75 anchor 計算單元分數。"""
    mat_anchor = unit_dist["material"]["p75"]
    att_anchor = unit_dist["attachment"]["p75"]
    ai_anchor = unit_dist["ai"]["p75"]

    has_any_answer = any(
        r["pre_count"] + r["post_count"] + r["chal_count"] > 0
        for r in unit_raw_by_student.values()
    )

    results = {}
    for s in students_rows:
        raw = unit_raw_by_student[s["user_id"]]
        parts = []
        if unit_has_material:
            sc = anchor_score(raw["read_material_min"], mat_anchor)
            if sc is not None:
                parts.append(sc)
        if unit_has_attachment:
            sc = anchor_score(raw["read_attach_min"], att_anchor)
            if sc is not None:
                parts.append(sc)
        if has_any_answer:
            parts.append(raw["answer_score"])
        sc = anchor_score(raw["ai_turns"], ai_anchor)
        if sc is not None:
            parts.append(sc)

        unit_score = round(sum(parts) / len(parts), 1) if parts else 0.0
        results[s["user_id"]] = unit_score
    return results


def main():
    engine = get_engine()
    with engine.connect() as conn:
        units = fetch_units(conn)
        students = fetch_students(conn)

        print(f"Units: {len(units)} | Students: {len(students)}")
        assert len(units) == 6, f"Expected 6 units, got {len(units)}"

        # 預先載入每單元的教材/附件清單
        unit_material_map = {u["unit_id"]: fetch_unit_material_ids(conn, u["unit_id"]) for u in units}
        unit_attach_map = {u["unit_id"]: fetch_unit_attachment_ids(conn, u["unit_id"]) for u in units}

        # 計算 raw + unit_score + 分佈統計
        # 結構：results[user_id][unit_id] = {raw..., "score": float}
        results = {s["user_id"]: {} for s in students}
        unit_dist_map = {}  # {unit_id: {material: {...}, attachment: {...}, ai: {...}}}

        for unit in units:
            uid = unit["unit_id"]
            unit_raw = {}
            for s in students:
                raw = compute_student_unit_raw(
                    conn, s["user_id"], uid,
                    unit_material_map[uid], unit_attach_map[uid]
                )
                unit_raw[s["user_id"]] = raw

            unit_has_material = len(unit_material_map[uid]) > 0
            unit_has_attachment = len(unit_attach_map[uid]) > 0

            unit_dist = compute_unit_distribution(students, unit_raw)
            unit_dist_map[uid] = unit_dist
            unit_scores = compute_unit_scores(students, unit_raw, unit_dist,
                                              unit_has_material, unit_has_attachment)

            for s in students:
                results[s["user_id"]][uid] = {**unit_raw[s["user_id"]], "score": unit_scores[s["user_id"]]}

        # --- 輸出 unit metric stats CSV ---
        stats_path = OUTPUT_DIR / "course_62_unit_metric_stats.csv"
        with open(stats_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([
                "topic_id", "unit_id", "單元名稱", "是否計分",
                "教材_零人數", "教材_中位數", "教材_平均", "教材_P75_anchor", "教材_P90", "教材_最大",
                "附件_零人數", "附件_中位數", "附件_平均", "附件_P75_anchor", "附件_P90", "附件_最大",
                "AI對話_零人數", "AI對話_中位數", "AI對話_平均", "AI對話_P75_anchor", "AI對話_P90", "AI對話_最大",
            ])
            for u in units:
                d = unit_dist_map[u["unit_id"]]
                used = "否" if u["topic_id"] in EXCLUDED_TOPIC_IDS else "是"
                w.writerow([
                    u["topic_id"], u["unit_id"], u["name"], used,
                    d["material"]["n_zero"], d["material"]["median"], d["material"]["mean"],
                    d["material"]["p75"], d["material"]["p90"], d["material"]["max"],
                    d["attachment"]["n_zero"], d["attachment"]["median"], d["attachment"]["mean"],
                    d["attachment"]["p75"], d["attachment"]["p90"], d["attachment"]["max"],
                    d["ai"]["n_zero"], d["ai"]["median"], d["ai"]["mean"],
                    d["ai"]["p75"], d["ai"]["p90"], d["ai"]["max"],
                ])
        print(f"Wrote {stats_path}")

        # detail/summary 皆排除 u1
        scored_units = [u for u in units if u["topic_id"] not in EXCLUDED_TOPIC_IDS]

        # --- 輸出 detail CSV ---
        detail_path = OUTPUT_DIR / "course_62_student_unit_detail.csv"
        with open(detail_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([
                "學號", "姓名", "unit_id", "topic_id", "單元名稱",
                "閱讀生成教材分鐘", "閱讀附件分鐘",
                "課前作答題數", "課後作答題數", "挑戰作答題數",
                "AI對話輪次", "作答正確率", "單元分數"
            ])
            for s in students:
                for u in scored_units:
                    r = results[s["user_id"]][u["unit_id"]]
                    w.writerow([
                        s["student_id"] or "", s["full_name"],
                        u["unit_id"], u["topic_id"], u["name"],
                        r["read_material_min"], r["read_attach_min"],
                        r["pre_count"], r["post_count"], r["chal_count"],
                        r["ai_turns"],
                        f"{r['correctness']*100:.1f}%",
                        r["score"],
                    ])
        print(f"Wrote {detail_path}")

        # --- 輸出 summary CSV ---
        summary_path = OUTPUT_DIR / "course_62_student_summary.csv"
        with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            # 表頭：學號, 姓名, 使用量分級, 學期平均分, + 每單元 8 欄（僅 u2..u6）
            header = ["學號", "姓名", "使用量分級", "學期平均分"]
            for u in scored_units:
                p = f"u{u['topic_id']}"
                header += [
                    f"{p}_閱讀生成教材分鐘", f"{p}_閱讀附件分鐘",
                    f"{p}_課前作答題數", f"{p}_課後作答題數", f"{p}_挑戰作答題數",
                    f"{p}_AI對話輪次", f"{p}_作答正確率", f"{p}_分數",
                ]
            w.writerow(header)

            n_scored = len(scored_units)

            # 先算每人 sem_avg
            def sem_avg_of(stu):
                scores = [results[stu["user_id"]][u["unit_id"]]["score"] for u in scored_units]
                return round(sum(scores) / n_scored, 1) if n_scored else 0.0

            sem_avgs = {s["user_id"]: sem_avg_of(s) for s in students}
            # 計算學期平均分的 P75 作為使用量分級 anchor
            sem_avg_p75 = round(percentile(list(sem_avgs.values()), 75), 2)
            print(f"Semester avg P75 anchor for 使用量分級: {sem_avg_p75}")

            # 依 sem_avg 由高至低排序
            sorted_students = sorted(students, key=lambda s: sem_avgs[s["user_id"]], reverse=True)

            for s in sorted_students:
                sem_avg = sem_avgs[s["user_id"]]
                grade = usage_grade(sem_avg, sem_avg_p75)

                row = [s["student_id"] or "", s["full_name"], grade, sem_avg]
                for u in scored_units:
                    r = results[s["user_id"]][u["unit_id"]]
                    row += [
                        r["read_material_min"], r["read_attach_min"],
                        r["pre_count"], r["post_count"], r["chal_count"],
                        r["ai_turns"],
                        f"{r['correctness']*100:.1f}%",
                        r["score"],
                    ]
                w.writerow(row)
        print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
