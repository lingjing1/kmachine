import os
import shutil
import sys
from sqlalchemy import text

# Add the project root to sys.path to allow importing backend modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.db import engine
from backend.app.config.settings import settings

def cleanup_multimodal_data():
    """
    清理所有與 Multimodal (圖片儲存改版) 相關的資料。
    包括資料庫表內容及本地實體圖片檔案。
    """
    print("🚀 啟動 Multimodal 資料清理腳本...")

    # 依照依賴關係排序或使用 CASCADE
    tables_to_truncate = [
        "submissions_assignment",
        "submissions_exam",
        "generated_content_chunks",
        "course_content_knowledge_points",
        "course_contents",
        "generated_contents",
        "document_kp_relationships",
        "document_knowledge_points",
        "document_chunks",
        "document_content",
        "attachments",
        "uploaded_contents",
        "unique_contents"
    ]

    try:
        with engine.connect() as conn:
            with conn.begin():
                print("\n--- 1. 資料庫表清理 ---")
                for table in tables_to_truncate:
                    # 使用 RESTART IDENTITY 重置 ID 計數，CASCADE 處理外鍵
                    conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
                    print(f"✅ 已清空表: {table}")

        print("\n--- 2. 物理圖片檔案清理 ---")
        # 清理 backend/storage/uploads/images/
        image_dir = os.path.join(settings.upload_dir, "images")
        if os.path.exists(image_dir):
            # 刪除所有子目錄 (doc_id 目錄)
            for item in os.listdir(image_dir):
                item_path = os.path.join(image_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"✅ 已移除圖片目錄: {item}")
                    elif os.path.isfile(item_path):
                        os.unlink(item_path)
                        print(f"✅ 已移除圖片檔案: {item}")
                except Exception as e:
                    print(f"❌ 移除 {item} 失敗: {e}")
        else:
            print(f"ℹ️ 圖片目錄不存在，略過: {image_dir}")

        print("\n✨ 清理完成！Multimodal 相關資料已全部重置。")
        print("💡 您現在可以啟動後端並重新上傳檔案進行測試。")

    except Exception as e:
        print(f"\n❌ 清理過程中發生錯誤: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("⚠️  警告：此操作將永久刪除所有文檔、生成內容、考卷、單元教材及學生繳交記錄。")
    confirm = input("確定要繼續嗎？(y/N): ")
    if confirm.lower() == 'y':
        cleanup_multimodal_data()
    else:
        print("操作已取消。")
