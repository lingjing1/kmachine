#!/usr/bin/env python3
"""
資料遷移腳本: knowledge_point_contents → course_contents
將 course_id = 3 的預覽內容遷移到 course_contents 表
"""
import json
from datetime import datetime
from sqlalchemy import text
from backend.app.utils.db_logger import engine

def migrate_kp_contents_to_course_contents():
    """
    執行資料遷移
    """
    print("=" * 100)
    print("資料遷移: knowledge_point_contents → course_contents")
    print("=" * 100)
    
    with engine.connect() as conn:
        # 開始交易
        trans = conn.begin()
        
        try:
            # 0. 暫時停用會造成問題的 trigger
            print("\n[步驟 0/5] 暫時停用 trigger...")
            conn.execute(text("ALTER TABLE course_contents DISABLE TRIGGER trg_sync_question_bank_usage"))
            print("✅ trigger 已停用")
            
            # 1. 讀取來源資料
            print("\n[步驟 1/4] 讀取來源資料...")
            source_query = text("""
                SELECT 
                    kpc.id,
                    kpc.knowledge_point_id,
                    kpc.unit_id,
                    kpc.course_id,
                    kpc.content_type,
                    kpc.title,
                    kpc.content_markdown,
                    kpc.content_plain,
                    kpc.created_at,
                    kpc.updated_at
                FROM knowledge_point_contents kpc
                WHERE kpc.course_id = 3
                ORDER BY kpc.id
            """)
            
            source_data = conn.execute(source_query).fetchall()
            print(f"✅ 讀取到 {len(source_data)} 筆來源資料")
            
            if len(source_data) == 0:
                print("⚠️  沒有資料需要遷移")
                return
            
            # 2. 轉換資料格式
            print("\n[步驟 2/4] 轉換資料格式...")
            insert_data = []
            
            for row in source_data:
                # 取得欄位值
                kp_id = row[1]
                unit_id = row[2]
                course_id = row[3]
                content_type_original = row[4]  # 'preview'
                title = row[5]
                content_markdown = row[6]
                content_plain = row[7]
                
                # 將 Markdown 純文字包裝成 JSON 字串格式 (符合 json 欄位要求)
                content_value = json.dumps(content_markdown)
                
                # 準備插入資料
                insert_record = {
                    'course_id': course_id,
                    'unit_id': unit_id,
                    'title': title,
                    'description': content_plain[:200] if content_plain else None,
                    'content_type': 'material',
                    'source_type': 'text',  # 使用 text 以符合純文字格式
                    'source_id': kp_id,
                    'content': content_value,  # 直接存 Markdown 純文字
                    'knowledge_point_id': kp_id,
                    'content_subtype': content_type_original,  # 'preview'
                    'is_published': True,
                    'is_visible': True,
                    'allow_review': True,
                    'include_in_grade': False
                }
                
                insert_data.append(insert_record)
            
            print(f"✅ 轉換完成 {len(insert_data)} 筆資料")
            
            # 3. 批次插入
            print("\n[步驟 3/4] 執行批次插入...")
            insert_query = text("""
                INSERT INTO course_contents (
                    course_id, unit_id, title, description,
                    content_type, source_type, source_id, content,
                    knowledge_point_id, content_subtype,
                    is_published, is_visible, allow_review, include_in_grade,
                    created_at, updated_at
                ) VALUES (
                    :course_id, :unit_id, :title, :description,
                    :content_type, :source_type, :source_id, :content,
                    :knowledge_point_id, :content_subtype,
                    :is_published, :is_visible, :allow_review, :include_in_grade,
                    NOW(), NOW()
                )
            """)
            
            # 執行批次插入
            for i, record in enumerate(insert_data, 1):
                conn.execute(insert_query, record)
                if i % 10 == 0:
                    print(f"  已插入 {i}/{len(insert_data)} 筆...")
            
            print(f"✅ 成功插入 {len(insert_data)} 筆資料")
            
            # 4. 驗證結果
            print("\n[步驟 4/4] 驗證遷移結果...")
            verify_query = text("""
                SELECT COUNT(*) 
                FROM course_contents 
                WHERE course_id = 3 
                  AND content_type = 'material'
                  AND source_type = 'text'
                  AND content_subtype = 'preview'
            """)
            
            verify_count = conn.execute(verify_query).scalar()
            print(f"✅ 驗證完成: course_contents 表中有 {verify_count} 筆符合條件的資料")
            
            # 5. 重新啟用 trigger
            print("\n[步驟 5/5] 重新啟用 trigger...")
            conn.execute(text("ALTER TABLE course_contents ENABLE TRIGGER trg_sync_question_bank_usage"))
            print("✅ trigger 已啟用")
            
            # 提交交易
            trans.commit()
            print("\n" + "=" * 100)
            print("✅ 遷移成功完成!")
            print("=" * 100)
            
            # 產生統計報告
            print("\n📊 遷移統計:")
            print(f"  - 來源資料筆數: {len(source_data)}")
            print(f"  - 成功插入筆數: {len(insert_data)}")
            print(f"  - 驗證查詢結果: {verify_count}")
            
            # 按單元統計
            unit_stats_query = text("""
                SELECT 
                    u.id,
                    u.name,
                    COUNT(*) as count
                FROM course_contents cc
                JOIN course_units u ON cc.unit_id = u.id
                WHERE cc.course_id = 3 
                  AND cc.content_type = 'material'
                  AND cc.source_type = 'text'
                  AND cc.content_subtype = 'preview'
                GROUP BY u.id, u.name
                ORDER BY u.id
            """)
            
            unit_stats = conn.execute(unit_stats_query).fetchall()
            print("\n📊 按單元統計:")
            for stat in unit_stats:
                print(f"  - 單元 {stat[0]} ({stat[1]}): {stat[2]} 筆")
            
        except Exception as e:
            # 發生錯誤時回滾
            trans.rollback()
            # 確保 trigger 被重新啟用
            try:
                conn.execute(text("ALTER TABLE course_contents ENABLE TRIGGER trg_sync_question_bank_usage"))
                print("✅ trigger 已重新啟用")
            except:
                pass
            print(f"\n❌ 遷移失敗: {e}")
            raise

if __name__ == "__main__":
    try:
        migrate_kp_contents_to_course_contents()
    except Exception as e:
        print(f"\n執行錯誤: {e}")
        import traceback
        traceback.print_exc()
