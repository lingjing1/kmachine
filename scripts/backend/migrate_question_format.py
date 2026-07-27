"""
資料遷移腳本：將舊格式題目轉換為新格式

舊格式 (手動新增):
{
  "answer": "...",
  "question": "...",
  "reference_pages": "...",
  "reference_content": "..."
}

新格式 (AI 生成):
{
  "type": "short_answer",
  "question_text": "...",
  "question_type": "short_answer",
  "sample_answer": "...",
  "source": {
    "evidence": "...",
    "chunk_ids": [],
    "match_score": null,
    "page_number": "..."
  },
  "question_number": null
}
"""

import json
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set.")

engine = create_engine(DATABASE_URL)


def convert_old_format_to_new(old_data: dict) -> dict:
    """
    將舊格式題目轉換為新格式
    
    Args:
        old_data: 舊格式的題目資料
        
    Returns:
        新格式的題目資料
    """
    # 判斷是否為舊格式 (有 "question" 和 "answer" 欄位)
    if "question" in old_data and "answer" in old_data:
        # 舊格式 -> 新格式轉換
        new_data = {
            "type": old_data.get("type", "short_answer"),  # 保留原有 type，預設為 short_answer
            "question_text": old_data["question"],
            "question_type": old_data.get("question_type", old_data.get("type", "short_answer")),
            "sample_answer": old_data["answer"],
            "source": {
                "evidence": old_data.get("reference_content", ""),
                "chunk_ids": [],  # 舊資料沒有 chunk_ids
                "match_score": None,  # 舊資料沒有 match_score
                "page_number": old_data.get("reference_pages", "")
            },
            "question_number": old_data.get("question_number")  # 保留原有編號
        }
        
        # 保留其他可能存在的欄位
        for key in ["points", "options", "correct_answer", "hint"]:
            if key in old_data:
                new_data[key] = old_data[key]
                
        return new_data
    else:
        # 已經是新格式，直接返回
        return old_data


def migrate_question_bank():
    """
    批量轉換資料庫中的題目格式
    """
    with engine.connect() as conn:
        try:
            # 查詢所有題目
            query = text("SELECT id, question_data FROM question_bank WHERE question_data IS NOT NULL")
            rows = conn.execute(query).fetchall()
            
            total = len(rows)
            converted = 0
            skipped = 0
            
            print(f"找到 {total} 個題目，開始轉換...")
            
            for row in rows:
                question_id = row[0]
                old_data = row[1]
                
                # 檢查是否為舊格式
                if "question" in old_data and "answer" in old_data:
                    # 轉換格式
                    new_data = convert_old_format_to_new(old_data)
                    
                    # 更新資料庫
                    update_query = text("""
                        UPDATE question_bank
                        SET question_data = CAST(:question_data AS jsonb)
                        WHERE id = :question_id
                    """)
                    conn.execute(update_query, {
                        "question_data": json.dumps(new_data, ensure_ascii=False),
                        "question_id": question_id
                    })
                    
                    converted += 1
                    print(f"✓ 已轉換題目 ID: {question_id}")
                else:
                    skipped += 1
                    print(f"- 跳過題目 ID: {question_id} (已是新格式)")
            
            conn.commit()
            
            print("\n" + "="*50)
            print(f"轉換完成！")
            print(f"總計: {total} 個題目")
            print(f"已轉換: {converted} 個")
            print(f"已跳過: {skipped} 個")
            print("="*50)
            
        except Exception as e:
            conn.rollback()
            print(f"錯誤: {e}")
            raise


def preview_conversion():
    """
    預覽轉換結果（不實際修改資料庫）
    """
    with engine.connect() as conn:
        try:
            query = text("SELECT id, question_data FROM question_bank WHERE question_data IS NOT NULL LIMIT 5")
            rows = conn.execute(query).fetchall()
            
            print("\n" + "="*50)
            print("預覽模式：前 5 筆資料轉換結果")
            print("="*50 + "\n")
            
            for row in rows:
                question_id = row[0]
                old_data = row[1]
                
                if "question" in old_data and "answer" in old_data:
                    new_data = convert_old_format_to_new(old_data)
                    
                    print(f"題目 ID: {question_id}")
                    print(f"舊格式: {json.dumps(old_data, ensure_ascii=False, indent=2)}")
                    print(f"新格式: {json.dumps(new_data, ensure_ascii=False, indent=2)}")
                    print("-" * 50 + "\n")
                else:
                    print(f"題目 ID: {question_id} - 已是新格式")
                    print("-" * 50 + "\n")
                    
        except Exception as e:
            print(f"錯誤: {e}")
            raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='題目格式轉換工具')
    parser.add_argument('--preview', action='store_true', help='預覽轉換結果（不實際修改）')
    parser.add_argument('--migrate', action='store_true', help='執行資料遷移')
    
    args = parser.parse_args()
    
    if args.preview:
        preview_conversion()
    elif args.migrate:
        confirm = input("確定要執行資料遷移嗎？此操作會修改資料庫。(yes/no): ")
        if confirm.lower() == 'yes':
            migrate_question_bank()
        else:
            print("已取消操作")
    else:
        print("請使用 --preview 預覽或 --migrate 執行遷移")
        print("範例：")
        print("  python3 migrate_question_format.py --preview")
        print("  python3 migrate_question_format.py --migrate")
