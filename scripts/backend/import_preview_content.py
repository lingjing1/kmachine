#!/usr/bin/env python3
"""
匯入 Preview Content 到 knowledge_point_contents 表

從 scripts/preview_content/*.csv 讀取資料並匯入資料庫
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


# Unit 對應表（CSV 檔案名 → DB unit name）
UNIT_MAPPING_FILE = 'scripts/unit_mapping.json'
PREVIEW_CONTENT_DIR = 'scripts/preview_content'
COURSE_ID = 3  # 1142 課程


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


def import_preview_content():
    """主要匯入函數"""
    print('=' * 80)
    print('開始匯入 Preview Content')
    print('=' * 80)
    
    # 載入 mapping
    unit_mapping = load_unit_mapping()
    
    with engine.connect() as conn:
        # 取得 DB mapping
        units, kps = get_unit_and_kp_mapping(conn)
        
        print(f'\n資料庫中有 {len(units)} 個 units, {len(kps)} 個 knowledge_points')
        
        # 遍歷所有 CSV 檔案
        csv_files = sorted(Path(PREVIEW_CONTENT_DIR).glob('*.csv'))
        
        total_imported = 0
        total_skipped = 0
        
        for csv_file in csv_files:
            print(f'\n處理檔案: {csv_file.name}')
            
            # 從檔案名提取 unit 名稱（去除 .csv 副檔名）
            unit_name_from_file = csv_file.stem  # 例如：A_機器學習-監督式學習
            
            # 轉換為 DB unit name
            db_unit_name = unit_mapping.get(unit_name_from_file)
            
            if not db_unit_name:
                print(f'  ❌ 找不到 unit mapping: {unit_name_from_file}')
                continue
            
            unit_id = units.get(db_unit_name)
            if not unit_id:
                print(f'  ❌ 資料庫中找不到 unit: {db_unit_name}')
                continue
            
            print(f'  ✅ Unit: {db_unit_name} (ID: {unit_id})')
            
            # 讀取 CSV
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            
            for idx, row in df.iterrows():
                kp_name = row['knowledge_point_name']
                
                # 查詢 knowledge_point_id
                kp_info = kps.get(kp_name)
                
                if not kp_info:
                    print(f'    ⚠️  找不到 KP: {kp_name}')
                    total_skipped += 1
                    continue
                
                kp_id = kp_info['id']
                kp_unit_id = kp_info['unit_id']
                
                # 驗證 unit_id 一致
                if kp_unit_id != unit_id:
                    print(f'    ⚠️  KP unit 不一致: {kp_name} (KP unit_id={kp_unit_id}, 檔案 unit_id={unit_id})')
                
                # 插入資料
                try:
                    conn.execute(text("""
                        INSERT INTO knowledge_point_contents 
                        (knowledge_point_id, unit_id, course_id, content_type, title, content_markdown, content_plain, created_at, updated_at)
                        VALUES 
                        (:kp_id, :unit_id, :course_id, 'preview', :title, :markdown, :plain, NOW(), NOW())
                        ON CONFLICT (knowledge_point_id, content_type) DO UPDATE
                        SET content_markdown = EXCLUDED.content_markdown,
                            content_plain = EXCLUDED.content_plain,
                            updated_at = NOW()
                    """), {
                        'kp_id': kp_id,
                        'unit_id': kp_unit_id,  # 使用 KP 自己的 unit_id
                        'course_id': COURSE_ID,
                        'title': kp_name,
                        'markdown': row['preview_content_markdown'],
                        'plain': row['preview_content_text']
                    })
                    
                    total_imported += 1
                    print(f'    ✅ {kp_name}')
                    
                except Exception as e:
                    print(f'    ❌ 匯入失敗: {kp_name} - {e}')
                    total_skipped += 1
        
        # Commit
        conn.commit()
        
        print('\n' + '=' * 80)
        print(f'匯入完成！')
        print(f'  成功: {total_imported} 筆')
        print(f'  跳過: {total_skipped} 筆')
        print('=' * 80)


if __name__ == '__main__':
    import_preview_content()
