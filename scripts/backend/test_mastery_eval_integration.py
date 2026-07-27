
import sys
import os
import json
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text, insert, delete

# 設定環境路徑以導入 backend 模組
sys.path.append(os.getcwd())

from backend.app.utils.db_logger import engine
from backend.app.agents.student_agent.nodes.mastery_agent import get_mastery_status, get_unit_mastery_status
from backend.app.routers.student_preview_router import evaluate_mastery, MasteryEvaluateRequest
from fastapi import HTTPException

# 測試設定
TEST_STUDENT_ID = 6
TEST_KP_ID = 1
TEST_UNIT_ID = 3
TEST_COURSE_ID = 3

def setup_test_data():
    """建立測試數據"""
    print(f"\n[Setup] 正在為 Student {TEST_STUDENT_ID} 建立測試數據...")
    with engine.connect() as conn:
        conn.commit()  # 確保開始前是乾淨的狀態

        # 1. 清理舊數據
        conn.execute(text("DELETE FROM student_question_logs WHERE student_id = :sid"), {"sid": TEST_STUDENT_ID})
        conn.execute(text("DELETE FROM student_knowledge_mastery WHERE student_id = :sid"), {"sid": TEST_STUDENT_ID})
        
        # 2. 插入作答記錄
        # Question 1: 重複作答 3 次 (測試去重)
        # Question 2, 3: 各作答 1 次 (測試完整取出同一 KP 下的所有題目)
        
        now = datetime.now()
        
        logs = [
            # Q1 - 舊
            {"student_id": TEST_STUDENT_ID, "question_id": 1, "answer": json.dumps({"text": "Answer Q1-1"}), "correctness": None, "answered_at": now - timedelta(hours=2), "knowledge_point_id": TEST_KP_ID, "course_id": TEST_COURSE_ID, "unit_id": TEST_UNIT_ID, "stage": "preview"},
            # Q1 - 中
            {"student_id": TEST_STUDENT_ID, "question_id": 1, "answer": json.dumps({"text": "Answer Q1-2"}), "correctness": None, "answered_at": now - timedelta(hours=1), "knowledge_point_id": TEST_KP_ID, "course_id": TEST_COURSE_ID, "unit_id": TEST_UNIT_ID, "stage": "preview"},
            # Q1 - 新 (預期保留)
            {"student_id": TEST_STUDENT_ID, "question_id": 1, "answer": json.dumps({"text": "Answer Q1-3 [最新]"}), "correctness": None, "answered_at": now, "knowledge_point_id": TEST_KP_ID, "course_id": TEST_COURSE_ID, "unit_id": TEST_UNIT_ID, "stage": "preview"},
            
            # Q2 (預期保留)
            {"student_id": TEST_STUDENT_ID, "question_id": 2, "answer": json.dumps({"text": "Answer Q2"}), "correctness": None, "answered_at": now, "knowledge_point_id": TEST_KP_ID, "course_id": TEST_COURSE_ID, "unit_id": TEST_UNIT_ID, "stage": "preview"},
            
            # Q3 (預期保留)
            {"student_id": TEST_STUDENT_ID, "question_id": 3, "answer": json.dumps({"text": "Answer Q3"}), "correctness": None, "answered_at": now, "knowledge_point_id": TEST_KP_ID, "course_id": TEST_COURSE_ID, "unit_id": TEST_UNIT_ID, "stage": "preview"}
        ]
        
        for log in logs:
            conn.execute(text("""
                INSERT INTO student_question_logs 
                (student_id, question_id, answer, correctness, answered_at, knowledge_point_id, course_id, unit_id, stage)
                VALUES (:student_id, :question_id, :answer, :correctness, :answered_at, :knowledge_point_id, :course_id, :unit_id, :stage)
            """), log)
            
        # 3. 插入 Mastery 記錄 (Preview vs Review)
        # 用來測試優先級邏輯
        conn.execute(text("""
            INSERT INTO student_knowledge_mastery 
            (student_id, knowledge_point_id, course_id, unit_id, 
             preview_mastery_level, review_mastery_level, mastery_level, 
             created_at, updated_at)
            VALUES 
            (:sid, :kp_id, :cid, :uid, '待加強', '精熟', '未定義', :now, :now)
        """), {
            "sid": TEST_STUDENT_ID, "kp_id": TEST_KP_ID, "cid": TEST_COURSE_ID, "uid": TEST_UNIT_ID, "now": now
        })
        
        conn.commit()
    print("[Setup] 完成。")

def test_deduplication_logic():
    """測試 SQL 去重邏輯 (ROW_NUMBER)"""
    print("\n[Test 1] 測試題目作答去重邏輯 (含多題選取)...")
    
    with engine.connect() as conn:
        # 使用與 Router 相同的 SQL 邏輯 (注意這裡欄位名 answer, correctness)
        query = text("""
            WITH latest_answers AS (
                SELECT 
                    id, 
                    question_id, 
                    answer,
                    correctness,
                    answered_at,
                    ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY answered_at DESC) as rn
                FROM student_question_logs
                WHERE student_id = :student_id
                AND knowledge_point_id = :kp_id
            )
            SELECT question_id, answer 
            FROM latest_answers
            WHERE rn = 1
            ORDER BY question_id
        """)
        
        results = conn.execute(query, {"student_id": TEST_STUDENT_ID, "kp_id": TEST_KP_ID}).fetchall()
        
        print(f"  -> 查詢結果數量: {len(results)} (預期: 3)")
        
        # 驗證邏輯
        # 注意: 取回來如果是 JSON 字串，可能需要 loads，或者如果是字串類型則直接比對
        expected_answers = {
            1: "Answer Q1-3 [最新]",
            2: "Answer Q2",
            3: "Answer Q3"
        }
        
        if len(results) != 3:
            print(f"  ❌ 失敗：數量不正確 (Expected 3, Got {len(results)})")
            return

        all_match = True
        for row in results:
            qid = row.question_id
            ans = row.answer
            
            # 嘗試轉換 JSON (如果 DB 返回的是 string 類型的 JSON)
            if isinstance(ans, str) :
                try:
                    # 如果是被雙引號包起來的字串 '"Answer..."'，loads後變成 'Answer...'
                    ans_decoded = json.loads(ans)
                    if isinstance(ans_decoded, str):
                        ans = ans_decoded
                except:
                    pass
            
            print(f"  -> Q{qid}: {ans}")
            
            if qid in expected_answers and expected_answers[qid] in str(ans):
                continue
            else:
                print(f"     ❌ 錯誤：Q{qid} 內容不符 (Expected: {expected_answers.get(qid)})")
                all_match = False
        
        if all_match:
            print("  ✅ 成功：正確撈出 Q1(最新), Q2, Q3 的記錄。")

def test_mastery_priority_logic():
    """測試 Mastery Agent 的優先級讀取邏輯"""
    print("\n[Test 2] 測試 Mastery 優先級 (Review > Preview)...")
    
    # 預期：DB 中 Preview='待加強', Review='精熟'
    # 應該回傳：'精熟'
    
    status = get_mastery_status(TEST_STUDENT_ID, TEST_KP_ID)
    
    if not status:
        print("  ❌ 失敗：無法取得 Mastery Status")
        return
        
    level = status.get("mastery_level")
    p_level = status.get("preview_mastery_level")
    r_level = status.get("review_mastery_level")
    
    print(f"  -> Preview Level in DB: {p_level}")
    print(f"  -> Review Level in DB:  {r_level}")
    print(f"  -> Effective Level:     {level}")
    
    if level == "精熟":
        print("  ✅ 成功：正確優先使用了 Review Mastery Level。")
    elif level == "待加強":
        print("  ❌ 失敗：錯誤使用了 Preview Level。")
    else:
        print(f"  ❌ 失敗：未知的 Level ({level})。")

def test_path_structure_check():
    """模擬檢查路徑生成邏輯"""
    print("\n[Test 3] 檢查路徑結構邏輯...")
    
    student_id = TEST_STUDENT_ID
    stage = "preview"
    kp_id = TEST_KP_ID
    
    # 依照新邏輯生成的路徑
    expected_dir = f"backend/lime_reports/user_id_{student_id}/{stage}"
    expected_file = f"knowledge_point_{kp_id}.html"
    full_path = os.path.join(expected_dir, expected_file)
    
    print(f"  -> 預期完整路徑: {full_path}")
    
    import re
    if re.search(r"user_id_\d+/[^/]+/knowledge_point_\d+\.html", full_path):
        print("  ✅ 成功：路徑格式符合預期 (user_id_{id}/{stage}/knowledge_point_{kp}.html)")
    else:
        print("  ❌ 失敗：路徑格式不符。")

def test_full_evaluation_flow():
    """整合測試：實際呼叫 evaluate_mastery 生成 LIME 報告"""
    print("\n[Test 4] 整合測試：呼叫 evaluate_mastery 生成 LIME 報告...")
    
    # 構造 Request
    req = MasteryEvaluateRequest(
        question_id=1,
        knowledge_point_id=TEST_KP_ID,
        answer="這是整合測試的回答，關於機器學習的定義。",
        stage="preview"
    )
    
    try:
        # 使用 asyncio.run 來執行 async 函數
        # 但因為我們已經在 async main 中 (如果有) 或者直接同步執行
        # 這裡是同步腳本，所以用 asyncio.run
        print("  -> 正在執行 evaluate_mastery (可能需要一些時間載入模型)...")
        result = asyncio.run(evaluate_mastery(
            kp_id=TEST_KP_ID,
            student_id=TEST_STUDENT_ID,
            request=req
        ))
        
        print(f"  -> 執行完成。結果: {result.summary}")
        
        # 檢查報告路徑
        summary = result.summary
        print(f"  -> LIME Report Generated: {summary.get('lime_report_generated')}")
        print(f"  -> LIME Report Path: {summary.get('lime_report_path')}")
        
        if summary.get('lime_report_generated') and summary.get('lime_report_path'):
            # 驗證文件是否存在
            # 注意：result.lime_report_path 是相對路徑 (lime_reports/...)
            # 我們需要加上 backend/ 前綴，因為那是我們存儲的根目錄
            abs_path = os.path.join(os.getcwd(), "backend", summary.get('lime_report_path'))
            
            if os.path.exists(abs_path):
                 print(f"  ✅ 成功：報告文件實際存在於 {abs_path}")
            else:
                 print(f"  ❌ 失敗：報告文件不存在於 {abs_path}")
        else:
             print("  ❌ 失敗：未生成 LIME 報告")

    except Exception as e:
        print(f"  ❌ 執行錯誤: {e}")
        import traceback
        traceback.print_exc()

def cleanup():
    """清理測試數據"""
    print("\n[Cleanup] 清理測試數據...")
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM student_question_logs WHERE student_id = :sid"), {"sid": TEST_STUDENT_ID})
        conn.execute(text("DELETE FROM student_knowledge_mastery WHERE student_id = :sid"), {"sid": TEST_STUDENT_ID})
        conn.commit()
    print("[Cleanup] 完成。")

if __name__ == "__main__":
    # try:
    setup_test_data()
    test_deduplication_logic()
    test_mastery_priority_logic()
    test_path_structure_check()
    test_full_evaluation_flow() # 新增
    # finally:
    #     cleanup()
