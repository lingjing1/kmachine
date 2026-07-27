"""
Teacher Kappa Evaluation Router
===============================

給教師用的「Kappa 評估中心」API（白名單：user_id 34 楊景元 / 6 nicole 測試）。

四個獨立評估任務（Task A/B 針對 course 62、Task C1/C2 針對 fine-tune CSV）：
  - Task A  course62_mastery       RoBERTa 掌握度 vs 教師  (3 類)
  - Task B  course62_polarity      LIME 關鍵字極性 vs 教師 (+/-)
  - Task C1 finetune_mastery       CSV Mastery_Label vs 教師 (3 類)
  - Task C2 finetune_performance   CSV 學生表現 vs 教師 (Correct/Partial/Incorrect)

每個任務都有三個 endpoint：
  GET  /{task}/samples            → 清單（回 SampleListResponse）
  GET  /{task}/samples/{id}       → 單筆完整資料（給評分頁用）
  PUT  /{task}/samples/{id}       → 提交或覆寫教師評分

另有一個 Dashboard 用的：
  GET  /overview                  → 4 任務的進度（total / completed）

註：κ 本身改由離線腳本計算，這裡只收資料，不算 κ。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text

from backend.app.db import engine
from backend.app.utils.auth_utils import get_current_user_id
from backend.app.schemas.kappa_eval_schemas import (
    Course62MasterySample,
    Course62MasterySubmit,
    Course62PolaritySample,
    Course62PolaritySubmit,
    FinetuneMasterySample,
    FinetuneMasterySubmit,
    FinetunePerformanceSample,
    FinetunePerformanceSubmit,
    OverviewResponse,
    PolarityItem,
    SampleListItem,
    SampleListResponse,
    TaskProgress,
    TeacherPolarityItem,
)

router = APIRouter(prefix="/api/teacher/kappa-eval", tags=["teacher-kappa-eval"])

# 白名單：只有這兩個 user_id 可以進入 Kappa 評估中心
ALLOWED_USER_IDS = {34, 6}


# ==================== Auth / 共用 helper ====================

def _guard(user_id: int = Depends(get_current_user_id)) -> int:
    """
    FastAPI dependency：從 JWT 解出 user_id，並檢查是否在白名單。
    不在 → 403；在 → 回傳 user_id 給 endpoint 當 teacher_id 用。
    """
    if user_id not in ALLOWED_USER_IDS:
        raise HTTPException(status_code=403, detail="此帳號未被授權進入 Kappa 評估中心")
    return user_id


def _iso(dt) -> Optional[str]:
    """把 datetime 轉 ISO 字串；None → None（給前端 JSON 用）"""
    return dt.isoformat() if dt is not None else None


# ==================== Overview / Dashboard ====================

# 四個任務的 (table_name, 用來判斷「已完成」的欄位)
# 只有這個欄位非 NULL，才算教師評完這筆樣本
_TASK_TABLES = {
    "course62_mastery": ("teacher_eval_course62_mastery", "teacher_mastery"),
    "course62_polarity": ("teacher_eval_course62_polarity", "teacher_polarities"),
    "finetune_mastery": ("teacher_eval_finetune_mastery", "teacher_mastery"),
    "finetune_performance": ("teacher_eval_finetune_performance", "teacher_performance"),
}


@router.get("/overview", response_model=OverviewResponse)
def overview(teacher_id: int = Depends(_guard)):
    """
    [GET /api/teacher/kappa-eval/overview]
    ---------------------------------------------------------------
    Dashboard 首頁用。
    一次查 4 張評估表，回傳該教師在每個任務的 total / completed。

    Returns:
        OverviewResponse {
            teacher_id: int,
            tasks: [
                {task: 'course62_mastery',       total: 54, completed: 12},
                {task: 'course62_polarity',      total: 54, completed: 12},
                {task: 'finetune_mastery',       total: 48, completed:  0},
                {task: 'finetune_performance',   total: 42, completed:  0},
            ]
        }
    """
    tasks = []
    with engine.connect() as conn:
        for task_name, (table, completed_col) in _TASK_TABLES.items():
            # COUNT(*) FILTER (WHERE col IS NOT NULL) 是 PG 的 conditional count
            row = conn.execute(
                text(f"""
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE {completed_col} IS NOT NULL) AS completed
                    FROM {table}
                    WHERE teacher_id = :t
                """),
                {"t": teacher_id},
            ).fetchone()
            tasks.append(TaskProgress(task=task_name, total=int(row[0] or 0), completed=int(row[1] or 0)))
    return OverviewResponse(teacher_id=teacher_id, tasks=tasks)


def _list_samples(table: str, completed_col_sql: str, task_name: str, teacher_id: int) -> SampleListResponse:
    """
    四個任務的「清單查詢」共用實作。
    回傳每筆樣本的 id / display_order / stratum / 是否已評 / 首次送出時間。
    不回完整 snapshot（那是 GET /samples/{id} 的工作）。

    Args:
        table: 資料表名稱
        completed_col_sql: 用來產生 is_completed 的 SQL 片段（例："(teacher_mastery IS NOT NULL)"）
        task_name: 回應中的 task 欄位值
        teacher_id: 目前教師 ID（來自 _guard）
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, display_order, stratum, {completed_col_sql} AS is_completed, submitted_at
                FROM {table}
                WHERE teacher_id = :t
                ORDER BY display_order
            """),
            {"t": teacher_id},
        ).fetchall()
    items = [
        SampleListItem(
            id=r[0],
            display_order=r[1],
            stratum=r[2],
            is_completed=bool(r[3]),
            submitted_at=_iso(r[4]),
        )
        for r in rows
    ]
    return SampleListResponse(
        task=task_name,
        total=len(items),
        completed=sum(1 for i in items if i.is_completed),
        items=items,
    )


# ==================== Task A：course62 掌握度（RoBERTa vs 教師）====================

@router.get("/course62-mastery/samples", response_model=SampleListResponse)
def list_course62_mastery(teacher_id: int = Depends(_guard)):
    """
    [GET /course62-mastery/samples]
    ---------------------------------------------------------------
    Task A 清單。列出這位教師在 course 62 掌握度任務的 54 筆樣本。
    教師前端載入評估頁時先打這支，渲染題號 1..54 的側邊欄。
    """
    return _list_samples(
        "teacher_eval_course62_mastery",
        "(teacher_mastery IS NOT NULL)",  # 有填 teacher_mastery 視為已評
        "course62_mastery",
        teacher_id,
    )


@router.get("/course62-mastery/samples/{sample_id}", response_model=Course62MasterySample)
def get_course62_mastery(sample_id: int = Path(...), teacher_id: int = Depends(_guard)):
    """
    [GET /course62-mastery/samples/{id}]
    ---------------------------------------------------------------
    Task A 單筆。回傳該題完整資料給評估頁渲染：
      - AI 原始預測（ai_mastery / ai_mastery_confidence）
      - 完整 LIME 報告（lime_report_json，含 bert_input、feature_weights...）
      - 教師現有答案（若尚未評為 None）
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, display_order, stratum, ai_mastery, ai_mastery_confidence,
                       lime_report_json, teacher_mastery, teacher_note, submitted_at
                FROM teacher_eval_course62_mastery
                WHERE id = :id AND teacher_id = :t
            """),
            {"id": sample_id, "t": teacher_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sample not found")
    return Course62MasterySample(
        id=row[0], display_order=row[1], stratum=row[2],
        ai_mastery=row[3], ai_mastery_confidence=row[4],
        lime_report_json=row[5] or {},
        teacher_mastery=row[6], teacher_note=row[7],
        submitted_at=_iso(row[8]),
    )


@router.put("/course62-mastery/samples/{sample_id}", response_model=Course62MasterySample)
def submit_course62_mastery(
    payload: Course62MasterySubmit,
    sample_id: int = Path(...),
    teacher_id: int = Depends(_guard),
):
    """
    [PUT /course62-mastery/samples/{id}]
    ---------------------------------------------------------------
    Task A 提交或覆寫評分。
    - 抽樣腳本已預填空殼 row，所以這裡只做 UPDATE，不新增
    - submitted_at 用 COALESCE 保留首次送出時間（教師若改分，updated_at 才會變）
    - 會驗證 teacher_mastery 必須是 待加強/尚可/精熟

    Request body: {teacher_mastery: '待加強'|'尚可'|'精熟', teacher_note?: string}
    """
    if payload.teacher_mastery not in {"待加強", "尚可", "精熟"}:
        raise HTTPException(status_code=400, detail="teacher_mastery 必須是 待加強/尚可/精熟")

    with engine.begin() as conn:
        updated = conn.execute(
            text("""
                UPDATE teacher_eval_course62_mastery
                SET teacher_mastery = :m,
                    teacher_note = :note,
                    submitted_at = COALESCE(submitted_at, now()),  -- 首次送出才寫
                    updated_at = now()                              -- 每次都更新
                WHERE id = :id AND teacher_id = :t
                RETURNING id
            """),
            {"id": sample_id, "t": teacher_id, "m": payload.teacher_mastery, "note": payload.teacher_note},
        ).fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="Sample not found")
    # 回傳更新後的完整資料，前端直接替換現況
    return get_course62_mastery(sample_id=sample_id, teacher_id=teacher_id)


# ==================== Task B：course62 LIME 極性（LIME 關鍵字 +/- vs 教師）====================

@router.get("/course62-polarity/samples", response_model=SampleListResponse)
def list_course62_polarity(teacher_id: int = Depends(_guard)):
    """
    [GET /course62-polarity/samples]
    ---------------------------------------------------------------
    Task B 清單。54 筆樣本（與 Task A 一一對應同 history_id，但獨立評分）。
    """
    return _list_samples(
        "teacher_eval_course62_polarity",
        "(teacher_polarities IS NOT NULL)",  # JSONB 非 NULL 代表教師已填
        "course62_polarity",
        teacher_id,
    )


@router.get("/course62-polarity/samples/{sample_id}", response_model=Course62PolaritySample)
def get_course62_polarity(sample_id: int = Path(...), teacher_id: int = Depends(_guard)):
    """
    [GET /course62-polarity/samples/{id}]
    ---------------------------------------------------------------
    Task B 單筆。
    回傳 ai_polarities（AI 那邊 keyword+weight+polarity+is_meta 完整列表）
    以及 teacher_polarities（教師現有答案，尚未評為 None）。
    前端要把 ai_polarities 每個 keyword 顯示給教師，讓他選 +/-。
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, display_order, stratum, lime_report_json,
                       ai_polarities, teacher_polarities, teacher_note, submitted_at
                FROM teacher_eval_course62_polarity
                WHERE id = :id AND teacher_id = :t
            """),
            {"id": sample_id, "t": teacher_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sample not found")

    # JSONB 從 DB 回來已是 Python list[dict]，轉成 Pydantic 物件
    ai_pols = [PolarityItem(**p) for p in (row[4] or [])]
    t_pols = None
    if row[5] is not None:
        t_pols = [TeacherPolarityItem(**p) for p in row[5]]

    return Course62PolaritySample(
        id=row[0], display_order=row[1], stratum=row[2],
        lime_report_json=row[3] or {},
        ai_polarities=ai_pols,
        teacher_polarities=t_pols,
        teacher_note=row[6],
        submitted_at=_iso(row[7]),
    )


@router.put("/course62-polarity/samples/{sample_id}", response_model=Course62PolaritySample)
def submit_course62_polarity(
    payload: Course62PolaritySubmit,
    sample_id: int = Path(...),
    teacher_id: int = Depends(_guard),
):
    """
    [PUT /course62-polarity/samples/{id}]
    ---------------------------------------------------------------
    Task B 提交或覆寫。
    驗證兩層：
      1. 每個 polarity 欄位只能是 '+' 或 '-'
      2. 教師送的 keyword 集合必須跟 AI 完全對齊（缺一個或多一個都不行）
         → 防止前端亂傳、保證後端 κ 計算時配對 100% 成功

    Request body: {teacher_polarities: [{keyword, polarity}], teacher_note?: string}
    """
    # --- 驗證 1：polarity 只能是 '+' 或 '-' ---
    for item in payload.teacher_polarities:
        if item.polarity not in {"+", "-"}:
            raise HTTPException(status_code=400, detail="polarity 必須是 '+' 或 '-'")

    # --- 驗證 2：keyword 集合必須跟 AI 對齊 ---
    with engine.connect() as conn:
        row = conn.execute(
            text("""SELECT ai_polarities FROM teacher_eval_course62_polarity
                    WHERE id=:id AND teacher_id=:t"""),
            {"id": sample_id, "t": teacher_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sample not found")
    ai_kws = {p["keyword"] for p in (row[0] or [])}
    t_kws = {i.keyword for i in payload.teacher_polarities}
    if t_kws != ai_kws:
        raise HTTPException(
            status_code=400,
            detail=f"teacher_polarities 關鍵字必須與 AI 對齊；缺少 {ai_kws - t_kws}，多餘 {t_kws - ai_kws}",
        )

    # --- 寫入（JSONB 存完整列表）---
    t_json = [i.model_dump() for i in payload.teacher_polarities]
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE teacher_eval_course62_polarity
                SET teacher_polarities = CAST(:p AS jsonb),
                    teacher_note = :note,
                    submitted_at = COALESCE(submitted_at, now()),
                    updated_at = now()
                WHERE id = :id AND teacher_id = :t
            """),
            {"id": sample_id, "t": teacher_id, "p": _json_dumps(t_json), "note": payload.teacher_note},
        )
    return get_course62_polarity(sample_id=sample_id, teacher_id=teacher_id)


# ==================== Task C1：fine-tune CSV 掌握度（CSV Mastery_Label vs 教師）====================

@router.get("/finetune-mastery/samples", response_model=SampleListResponse)
def list_finetune_mastery(teacher_id: int = Depends(_guard)):
    """
    [GET /finetune-mastery/samples]
    ---------------------------------------------------------------
    Task C1 清單。48 筆 CSV 列（每列代表一位學生在一章節的作答紀錄 + LLM 判定的 Mastery_Label）。
    """
    return _list_samples(
        "teacher_eval_finetune_mastery",
        "(teacher_mastery IS NOT NULL)",
        "finetune_mastery",
        teacher_id,
    )


@router.get("/finetune-mastery/samples/{sample_id}", response_model=FinetuneMasterySample)
def get_finetune_mastery(sample_id: int = Path(...), teacher_id: int = Depends(_guard)):
    """
    [GET /finetune-mastery/samples/{id}]
    ---------------------------------------------------------------
    Task C1 單筆。
    csv_row 是整列 CSV 內容（user_id、username、chapter、section、Short_Answer_Log...）。
    前端應渲染 Short_Answer_Log 讓教師讀完後判定 待加強/尚可/精熟。
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, display_order, stratum, csv_row,
                       ai_mastery, teacher_mastery, teacher_note, submitted_at
                FROM teacher_eval_finetune_mastery
                WHERE id = :id AND teacher_id = :t
            """),
            {"id": sample_id, "t": teacher_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sample not found")
    return FinetuneMasterySample(
        id=row[0], display_order=row[1], stratum=row[2],
        csv_row=row[3] or {}, ai_mastery=row[4],
        teacher_mastery=row[5], teacher_note=row[6],
        submitted_at=_iso(row[7]),
    )


@router.put("/finetune-mastery/samples/{sample_id}", response_model=FinetuneMasterySample)
def submit_finetune_mastery(
    payload: FinetuneMasterySubmit,
    sample_id: int = Path(...),
    teacher_id: int = Depends(_guard),
):
    """
    [PUT /finetune-mastery/samples/{id}]
    ---------------------------------------------------------------
    Task C1 提交或覆寫（邏輯與 Task A 完全相同，只是換資料表）。
    """
    if payload.teacher_mastery not in {"待加強", "尚可", "精熟"}:
        raise HTTPException(status_code=400, detail="teacher_mastery 必須是 待加強/尚可/精熟")
    with engine.begin() as conn:
        updated = conn.execute(
            text("""
                UPDATE teacher_eval_finetune_mastery
                SET teacher_mastery = :m,
                    teacher_note = :note,
                    submitted_at = COALESCE(submitted_at, now()),
                    updated_at = now()
                WHERE id = :id AND teacher_id = :t
                RETURNING id
            """),
            {"id": sample_id, "t": teacher_id, "m": payload.teacher_mastery, "note": payload.teacher_note},
        ).fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="Sample not found")
    return get_finetune_mastery(sample_id=sample_id, teacher_id=teacher_id)


# ==================== Task C2：fine-tune CSV 學生表現（LLM 判定 vs 教師）====================

@router.get("/finetune-performance/samples", response_model=SampleListResponse)
def list_finetune_performance(teacher_id: int = Depends(_guard)):
    """
    [GET /finetune-performance/samples]
    ---------------------------------------------------------------
    Task C2 清單。42 題（從 845 題題庫分層抽出，每類 14 題）。
    每筆是「單一題目 × 單一學生」的作答紀錄，非整列 CSV。
    """
    return _list_samples(
        "teacher_eval_finetune_performance",
        "(teacher_performance IS NOT NULL)",
        "finetune_performance",
        teacher_id,
    )


@router.get("/finetune-performance/samples/{sample_id}", response_model=FinetunePerformanceSample)
def get_finetune_performance(sample_id: int = Path(...), teacher_id: int = Depends(_guard)):
    """
    [GET /finetune-performance/samples/{id}]
    ---------------------------------------------------------------
    Task C2 單筆。
    question_snapshot 是單題完整資訊：question、reference_answer、student_answer、chapter、section。
    前端渲染題目三行，教師選 Correct / Partially Correct / Incorrect。
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, display_order, stratum, question_snapshot,
                       ai_performance, teacher_performance, teacher_note, submitted_at
                FROM teacher_eval_finetune_performance
                WHERE id = :id AND teacher_id = :t
            """),
            {"id": sample_id, "t": teacher_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sample not found")
    return FinetunePerformanceSample(
        id=row[0], display_order=row[1], stratum=row[2],
        question_snapshot=row[3] or {}, ai_performance=row[4],
        teacher_performance=row[5], teacher_note=row[6],
        submitted_at=_iso(row[7]),
    )


@router.put("/finetune-performance/samples/{sample_id}", response_model=FinetunePerformanceSample)
def submit_finetune_performance(
    payload: FinetunePerformanceSubmit,
    sample_id: int = Path(...),
    teacher_id: int = Depends(_guard),
):
    """
    [PUT /finetune-performance/samples/{id}]
    ---------------------------------------------------------------
    Task C2 提交或覆寫。
    Request body: {teacher_performance: 'Correct'|'Partially Correct'|'Incorrect', teacher_note?}
    """
    if payload.teacher_performance not in {"Correct", "Partially Correct", "Incorrect"}:
        raise HTTPException(status_code=400, detail="teacher_performance 必須是 Correct/Partially Correct/Incorrect")
    with engine.begin() as conn:
        updated = conn.execute(
            text("""
                UPDATE teacher_eval_finetune_performance
                SET teacher_performance = :p,
                    teacher_note = :note,
                    submitted_at = COALESCE(submitted_at, now()),
                    updated_at = now()
                WHERE id = :id AND teacher_id = :t
                RETURNING id
            """),
            {"id": sample_id, "t": teacher_id, "p": payload.teacher_performance, "note": payload.teacher_note},
        ).fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="Sample not found")
    return get_finetune_performance(sample_id=sample_id, teacher_id=teacher_id)


# ==================== Small helper ====================

def _json_dumps(obj):
    """JSON 序列化（保留中文不轉 \\u）給 Task B 的 JSONB UPDATE 用"""
    import json
    return json.dumps(obj, ensure_ascii=False)
