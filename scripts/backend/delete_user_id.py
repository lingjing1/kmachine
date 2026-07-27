import sys
import os
from sqlalchemy import text
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.app.db import engine

USER_ID_TO_DELETE = 23

def delete_user_and_related_data(user_id):
    fk_query = """
    SELECT tc.table_name, kcu.column_name 
    FROM information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu 
      ON tc.constraint_name = kcu.constraint_name 
      AND tc.table_schema = kcu.table_schema 
    JOIN information_schema.constraint_column_usage AS ccu 
      ON ccu.constraint_name = tc.constraint_name 
      AND ccu.table_schema = tc.table_schema 
    WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='users' AND ccu.column_name='id';
    """
    
    to_delete_summary = []
    user_info = None
    job_ids = []
    course_ids = []

    # --- 第一階段：統計資料 (獨立 Connection) ---
    with engine.connect() as conn:
        print(f"--- 準備刪除使用者 ID: {user_id} ---")
        
        # 取得基本資訊
        user_info = conn.execute(text("SELECT email, full_name FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        if not user_info:
            print(f"錯誤: 找不到使用者 ID {user_id}")
            return
        print(f"使用者名稱: {user_info.full_name} ({user_info.email})")
        
        # 統計直接關聯表
        fk_tables = conn.execute(text(fk_query)).fetchall()
        for table_name, column_name in fk_tables:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :user_id"), {"user_id": user_id}).scalar()
            if count > 0:
                to_delete_summary.append((table_name, count, f"DELETE FROM {table_name} WHERE {column_name} = :user_id"))

        # 統計間接關聯 (orchestration_jobs 系列)
        jobs_q = text("SELECT id FROM orchestration_jobs WHERE user_id = :user_id")
        job_ids = [row[0] for row in conn.execute(jobs_q, {"user_id": user_id}).fetchall()]
        if job_ids:
            task_count = conn.execute(text("SELECT COUNT(*) FROM agent_tasks WHERE job_id = ANY(:job_ids)"), {"job_ids": job_ids}).scalar()
            source_count = conn.execute(text("SELECT COUNT(*) FROM agent_task_sources WHERE job_id = ANY(:job_ids)"), {"job_ids": job_ids}).scalar()
            if task_count > 0: to_delete_summary.append(("agent_tasks", task_count, f"DELETE FROM agent_tasks WHERE job_id = ANY({job_ids})"))
            if source_count > 0: to_delete_summary.append(("agent_task_sources", source_count, f"DELETE FROM agent_task_sources WHERE job_id = ANY({job_ids})"))

        # 統計間接關聯 (courses 系列)
        courses_q = text("SELECT id FROM courses WHERE teacher_id = :user_id")
        course_ids = [row[0] for row in conn.execute(courses_q, {"user_id": user_id}).fetchall()]
        if course_ids:
            content_count = conn.execute(text("SELECT COUNT(*) FROM course_contents WHERE course_id = ANY(:course_ids)"), {"course_ids": course_ids}).scalar()
            unit_count = conn.execute(text("SELECT COUNT(*) FROM course_units WHERE course_id = ANY(:course_ids)"), {"course_ids": course_ids}).scalar()
            if content_count > 0: to_delete_summary.append(("course_contents", content_count, f"DELETE FROM course_contents WHERE course_id = ANY({course_ids})"))
            if unit_count > 0: to_delete_summary.append(("course_units", unit_count, f"DELETE FROM course_units WHERE course_id = ANY({course_ids})"))

    # --- 第二階段：顯示結果並等待確認 ---
    if not to_delete_summary:
        print("目前沒有發現相關關聯資料。")
    else:
        print("\n待刪除的關聯資料統計：")
        for table, count, _ in to_delete_summary:
            print(f" - [{table}]: {count} 筆資料")
    print(f" - [users]: 1 筆資料 (ID: {user_id})")
    
    confirm = input("\n確定要執行刪除嗎？請輸入 'yes' 確認，輸入其他文字則取消: ").strip().lower()
    if confirm != 'yes':
        print("操作已取消。")
        return

    # --- 第三階段：執行刪除 (新的 Connection 啟動交易) ---
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("\n正在執行刪除動作...")
            # 執行所有統計到的刪除指令
            for table, count, delete_sql in to_delete_summary:
                if "ANY" in delete_sql:
                    if "job_ids" in delete_sql:
                        conn.execute(text(f"DELETE FROM {table} WHERE job_id = ANY(:job_ids)"), {"job_ids": job_ids})
                    elif "course_ids" in delete_sql:
                        conn.execute(text(f"DELETE FROM {table} WHERE course_id = ANY(:course_ids)"), {"course_ids": course_ids})
                else:
                    conn.execute(text(delete_sql), {"user_id": user_id})
                print(f"已清理 [{table}]")

            # 刪除使用者主表
            conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            print(f"已刪除 [users] 使用者 {user_id}")
            
            trans.commit()
            print("\n✅ 所有資料已成功刪除並提交。")
        except Exception as e:
            trans.rollback()
            print(f"\n❌ 發生錯誤: {e}")
            print("交易已回滾，資料未變動。")

if __name__ == "__main__":
    # 支援從命令列帶入 ID
    target_id = USER_ID_TO_DELETE
    if len(sys.argv) > 1:
        try:
            target_id = int(sys.argv[1])
        except ValueError:
            print(f"錯誤: '{sys.argv[1]}' 不是有效的數字 ID")
            sys.exit(1)
            
    delete_user_and_related_data(target_id)
