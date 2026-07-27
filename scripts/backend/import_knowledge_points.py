#!/usr/bin/env python3
"""
知識點批次匯入腳本

此腳本會將 JSON 格式的知識點資料匯入到資料庫中。
對於每個 chapter，會先在 COURSE_UNITS 中查找或建立對應的 Unit，
然後批次插入該 chapter 下的所有知識點。

使用方式:
    python import_knowledge_points.py --course-id 3 --json-file knowledge_points.json
"""

import json
import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 取得資料庫 URL
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("錯誤：找不到 DATABASE_URL 環境變數")
    sys.exit(1)

from sqlalchemy import create_engine, text

# 建立資料庫引擎
engine = create_engine(DATABASE_URL)


def load_json_file(file_path: str) -> list:
    """載入 JSON 檔案"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_or_create_unit(conn, course_id: int, chapter_name: str, topic_id: int) -> int:
    """
    查找或建立 COURSE_UNIT
    
    Args:
        conn: 資料庫連線
        course_id: 課程 ID
        chapter_name: 章節名稱
        topic_id: Topic ID (用於排序)
    
    Returns:
        unit_id: COURSE_UNIT 的 ID
    """
    # 先嘗試查找現有的 Unit (按名稱匹配)
    find_query = text("""
        SELECT id FROM course_units 
        WHERE course_id = :course_id AND name = :name
        LIMIT 1
    """)
    
    result = conn.execute(find_query, {
        'course_id': course_id,
        'name': chapter_name
    }).fetchone()
    
    if result:
        print(f"  ✓ 找到現有 Unit: {chapter_name} (ID: {result[0]})")
        return result[0]
    
    # 如果沒找到，建立新的 Unit
    insert_query = text("""
        INSERT INTO course_units (course_id, topic_id, name, description)
        VALUES (:course_id, :topic_id, :name, :description)
        RETURNING id
    """)
    
    result = conn.execute(insert_query, {
        'course_id': course_id,
        'topic_id': topic_id,
        'name': chapter_name,
        'description': None
    }).fetchone()
    
    unit_id = result[0]
    print(f"  ✓ 建立新 Unit: {chapter_name} (ID: {unit_id})")
    return unit_id


def import_knowledge_points(conn, unit_id: int, course_id: int, knowledge_points: list):
    """
    批次匯入知識點
    
    Args:
        conn: 資料庫連線
        unit_id: Unit ID
        course_id: 課程 ID
        knowledge_points: 知識點名稱列表
    """
    # 先刪除該 Unit 現有的知識點（避免重複）
    delete_query = text("""
        DELETE FROM knowledge_points 
        WHERE unit_id = :unit_id AND course_id = :course_id
    """)
    conn.execute(delete_query, {'unit_id': unit_id, 'course_id': course_id})
    
    # 批次插入知識點
    insert_query = text("""
        INSERT INTO knowledge_points (unit_id, course_id, name, display_order)
        VALUES (:unit_id, :course_id, :name, :display_order)
    """)
    
    for idx, kp_name in enumerate(knowledge_points, start=1):
        conn.execute(insert_query, {
            'unit_id': unit_id,
            'course_id': course_id,
            'name': kp_name,
            'display_order': idx
        })
    
    print(f"    ✓ 匯入 {len(knowledge_points)} 個知識點")


def main():
    parser = argparse.ArgumentParser(description='批次匯入知識點')
    parser.add_argument('--course-id', type=int, required=True, help='課程 ID')
    parser.add_argument('--json-file', type=str, required=True, help='JSON 檔案路徑')
    parser.add_argument('--dry-run', action='store_true', help='測試模式，不實際寫入資料庫')
    
    args = parser.parse_args()
    
    # 載入 JSON
    print(f"\n📂 載入 JSON 檔案: {args.json_file}")
    data = load_json_file(args.json_file)
    print(f"✓ 找到 {len(data)} 個章節\n")
    
    # 連接資料庫
    with engine.connect() as conn:
        # 開始交易
        with conn.begin():
            for idx, item in enumerate(data, start=1):
                chapter = item['chapter']
                kps = item['Knowledge_points']
                
                print(f"[{idx}/{len(data)}] 處理章節: {chapter}")
                print(f"  知識點數量: {len(kps)}")
                
                if args.dry_run:
                    print(f"  [DRY RUN] 跳過實際匯入")
                    continue
                
                # 查找或建立 Unit
                unit_id = find_or_create_unit(conn, args.course_id, chapter, idx)
                
                # 匯入知識點
                if kps:
                    import_knowledge_points(conn, unit_id, args.course_id, kps)
                else:
                    print(f"    ⚠ 此章節沒有知識點")
                
                print()
        
        if not args.dry_run:
            print("✅ 所有知識點已成功匯入！")
        else:
            print("✅ 測試模式完成 (未實際寫入)")
    
    # 顯示統計資訊
    with engine.connect() as conn:
        count_query = text("""
            SELECT COUNT(*) FROM knowledge_points WHERE course_id = :course_id
        """)
        total = conn.execute(count_query, {'course_id': args.course_id}).scalar()
        print(f"\n📊 課程 {args.course_id} 目前總共有 {total} 個知識點")


if __name__ == '__main__':
    main()
