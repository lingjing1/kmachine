"""
Test script for Knowledge Point Extraction
Uses unique_content_id=100 to test KP extraction
"""

import asyncio
import os
import sys

# Set PYTHONPATH
sys.path.insert(0, '/home/monica/Cook.ai')

from backend.app.services.kp_extractor import extract_knowledge_points, extract_document_summary
from backend.app.config.settings import settings
from sqlalchemy import create_engine, MetaData, Table, select, text
import json

# Database setup
DATABASE_URL = settings.database_url
engine = create_engine(DATABASE_URL)
metadata = MetaData()


async def test_kp_extraction():
    """測試 KP 提取功能"""
    
    print("🚀 Knowledge Point Extraction Test")
    print("="*60)
    
    with engine.connect() as conn:
        # 1. 從資料庫獲取 unique_content_id=100 的文件內容
        print("\n=== 步驟 1: 獲取文件內容 ===")
        result = conn.execute(text("""
            SELECT 
                uc.id,
                uc.original_file_type,
                uploaded.file_name,
                dc.combined_human_text,
                dc.page_number
            FROM unique_contents uc
            LEFT JOIN uploaded_contents uploaded ON uploaded.unique_content_id = uc.id
            LEFT JOIN document_content dc ON dc.unique_content_id = uc.id
            WHERE uc.id = 100
            ORDER BY dc.page_number
        """))
        
        rows = result.fetchall()
        
        if not rows:
            print("❌ 找不到 unique_content_id=100 的文件")
            return
        
        file_name = rows[0][2] or "未知檔案"
        print(f"檔案名稱: {file_name}")
        print(f"檔案類型: {rows[0][1]}")
        print(f"總頁數: {len(rows)}")
        
        # 2. 組裝頁面資料
        pages = []
        for row in rows:
            if row[3]:  # combined_human_text
                pages.append({
                    'text': row[3],
                    'page_number': row[4],
                    'metadata': {}
                })
        
        if not pages:
            print("❌ 文件沒有內容")
            return
        
        # 3. 提取文件摘要
        print("\n=== 步驟 2: 提取文件摘要 ===")
        document_summary = extract_document_summary(pages)
        print(f"摘要長度: {len(document_summary)} 字元")
        print(f"\n前 500 字:\n{document_summary[:500]}...\n")
        
        # 4. 呼叫 KP 提取
        print("=== 步驟 3: 呼叫 LLM 提取知識點 ===")
        kp_result = await extract_knowledge_points(
            document_summary=document_summary,
            file_name=file_name
        )
        
        # 5. 顯示結果
        print("\n" + "="*60)
        print("📊 提取結果")
        print("="*60)
        
        print(f"\n✅ 成功提取 {len(kp_result['knowledge_points'])} 個知識點\n")
        
        # 按層級分組顯示
        for level in ['big_idea', 'core_concept', 'sub_technique']:
            kps_of_level = [kp for kp in kp_result['knowledge_points'] if kp.get('level') == level]
            if kps_of_level:
                level_name = {
                    'big_idea': '🎯 大概念 (Big Ideas)',
                    'core_concept': '💡 核心概念 (Core Concepts)',
                    'sub_technique': '🔧 子技術 (Sub-techniques)'
                }[level]
                
                print(f"\n{level_name}:")
                for kp in kps_of_level:
                    confidence = kp.get('confidence', 0)
                    confidence_icon = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.7 else "🔴"
                    print(f"  {confidence_icon} {kp['name']} (信心: {confidence:.2f})")
                    print(f"     {kp.get('description', 'N/A')}")
                    if kp.get('parent_mermaid_id'):
                        print(f"     └─ 父節點: {kp['parent_mermaid_id']}")
        
        # 顯示關係
        if kp_result.get('relationships'):
            print(f"\n🔗 知識點關係 ({len(kp_result['relationships'])} 個):")
            for rel in kp_result['relationships']:
                rel_type_icon = {
                    'prerequisite': '先備知識',
                    'composition': '包含',
                    'contrast': '比較',
                    'extension': '進階'
                }.get(rel['type'], rel['type'])
                
                print(f"  {rel['from']} {rel_type_icon} {rel['to']}")
        
        # 顯示 Mermaid 圖表
        if kp_result.get('mermaid_graph'):
            print(f"\n📈 Mermaid 圖表:")
            print("```mermaid")
            print(kp_result['mermaid_graph'])
            print("```")
        
        # 儲存結果到檔案
        output_file = "/tmp/kp_extraction_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(kp_result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 完整結果已儲存至: {output_file}")


if __name__ == "__main__":
    try:
        asyncio.run(test_kp_extraction())
        print("\n✅ 測試完成")
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
