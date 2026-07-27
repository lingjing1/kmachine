#!/usr/bin/env python3
"""
匯入簡答題到 question_bank 表

從 scripts/short_answer_question/1142_short_answer_consolidated.csv 讀取 122 題並匯入
"""
import os
import sys
import pandas as pd
import json
from pathlib import Path

# 加入專案路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.utils.db_logger import engine
from sqlalchemy import text


# 設定
QUESTION_CSV = 'scripts/short_answer_question/1142_short_answer_consolidated.csv'
UNIT_MAPPING_FILE = 'scripts/unit_mapping.json'
COURSE_ID = 3  # 1142 課程
CREATOR_ID = 15  # 使用者 ID


def load_unit_mapping():
    """載入 unit mapping"""
    with open(UNIT_MAPPING_FILE, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    return {item['from_unit']: item['to_unit'] for item in mapping}


def get_unit_and_kp_mapping(conn):
    """取得資料庫中的 unit 和 knowledge_point 對應"""
    # 取得所有 units
    result = conn.execute(text("""
        SELECT id, name FROM course_units WHERE course_id = :course_id
    """), {'course_id': COURSE_ID})
    
    units = {row[1]: row[0] for row in result.fetchall()}
    
    # 取得所有 knowledge points
    result = conn.execute(text("""
        SELECT id, unit_id, name 
        FROM knowledge_points 
        WHERE course_id = :course_id
    """), {'course_id': COURSE_ID})
    
    kps = {}
    for kp_id, unit_id, kp_name in result.fetchall():
        kps[kp_name] = {'id': kp_id, 'unit_id': unit_id}
    
    return units, kps


def import_questions():
    """主要匯入函數"""
    print('=' * 80)
    print('開始匯入簡答題到 question_bank')
    print('=' * 80)
    
    # 載入 mapping
    unit_mapping = load_unit_mapping()
    
    # 讀取 CSV
    df = pd.read_csv(QUESTION_CSV, encoding='utf-8-sig')
    print(f'\nCSV 檔案共有 {len(df)} 題')
    
    with engine.connect() as conn:
        # 取得 DB mapping
        units, kps = get_unit_and_kp_mapping(conn)
        
        total_imported = 0
        total_skipped = 0
        
        for idx, row in df.iterrows():
            # 轉換章節名稱
            chapter_from_csv = row['章節']
            db_unit_name = unit_mapping.get(chapter_from_csv)
            
            if not db_unit_name:
                print(f'{idx+1}. ❌ 找不到 unit mapping: {chapter_from_csv}')
                total_skipped += 1
                continue
            
            unit_id = units.get(db_unit_name)
            if not unit_id:
                print(f'{idx+1}. ❌ 資料庫中找不到 unit: {db_unit_name}')
                total_skipped += 1
                continue
            
            # 取得知識點
            kp_name = row['知識點']
            kp_info = kps.get(kp_name)
            
            if not kp_info:
                print(f'{idx+1}. ❌ 找不到 KP: {kp_name}')
                total_skipped += 1
                continue
            
            kp_id = kp_info['id']
            kp_unit_id = kp_info['unit_id']
            
            # 建構 question_data (JSONB)
            question_data = {
                'question': row['題目'],
                'answer': row['答案'],
                'reference_content': row['參考內容'] if pd.notna(row.get('參考內容')) else None,
                'reference_pages': row['參考頁碼'] if pd.notna(row.get('參考頁碼')) else None
            }
            
            # 建構 tags (來源資訊)
            tags = []
            if pd.notna(row.get('來源')):
                tags.append(row['來源'])
            
            # 建構 title: {unit_name}_{kp_name}簡答題
            title = f"{db_unit_name}_{kp_name}簡答題"
            
            # 插入資料
            try:
                # 轉換 tags 為 PostgreSQL 陣列格式
                tags_value = f'{{{",".join(tags)}}}' if tags else '{}'
                
                conn.execute(text("""
                    INSERT INTO question_bank 
                    (course_id, creator_id, title, question_data, question_type, difficulty_level, unit_id, kp_id, tags, is_published, created_at, updated_at)
                    VALUES 
                    (:course_id, :creator_id, :title, CAST(:question_data AS jsonb), 'short_answer', NULL, :unit_id, :kp_id, CAST(:tags AS text[]), true, NOW(), NOW())
                """), {
                    'course_id': COURSE_ID,
                    'creator_id': CREATOR_ID,
                    'title': title,
                    'question_data': json.dumps(question_data, ensure_ascii=False),
                    'unit_id': kp_unit_id,
                    'kp_id': kp_id,
                    'tags': tags_value
                })
                
                total_imported += 1
                if (total_imported) % 10 == 0:
                    print(f'  已匯入 {total_imported} 題...')
                
            except Exception as e:
                print(f'{idx+1}. ❌ 匯入失敗: {kp_name} - {e}')
                total_skipped += 1
        
        # Commit
        conn.commit()
        
        print('\n' + '=' * 80)
        print(f'匯入完成！')
        print(f'  成功: {total_imported} 題')
        print(f'  跳過: {total_skipped} 題')
        print('=' * 80)
        
        # 驗證
        result = conn.execute(text("""
            SELECT COUNT(*) FROM question_bank 
            WHERE course_id = :course_id AND question_type = 'short_answer'
        """), {'course_id': COURSE_ID})
        
        count = result.scalar()
        print(f'\n✅ 資料庫中共有 {count} 題簡答題')


if __name__ == '__main__':
    import_questions()
