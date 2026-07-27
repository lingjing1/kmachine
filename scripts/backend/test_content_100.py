"""
測試 unique_content_id=100 的完整 RAG 流程
包含：重新 chunking + hybrid search + 生成測試
"""
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, text
from backend.app.config.settings import settings
from backend.app.agents.rag_agent import rag_agent
import json

def check_content_100():
    """檢查 content_id=100 是否存在"""
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM unique_contents WHERE id = 100")
        ).fetchone()
        
        if not result:
            print("❌ unique_content_id=100 不存在")
            # 列出可用的 IDs
            available = conn.execute(text("SELECT id FROM unique_contents ORDER BY id DESC LIMIT 5")).fetchall()
            print(f"可用的 content IDs: {[r[0] for r in available]}")
            return False
        
        print(f"✓ 找到文件: ID={result[0]}")
        
        # 檢查 chunks
        chunk_count = conn.execute(
            text("SELECT COUNT(*) FROM document_chunks WHERE unique_content_id = 100")
        ).scalar()
        print(f"✓ 現有 {chunk_count} 個 chunks")
        
        # 檢查 chunk size 分布
        chunk_sizes = conn.execute(
            text("""
                SELECT 
                    MIN(LENGTH(chunk_text)) as min_size,
                    MAX(LENGTH(chunk_text)) as max_size,
                    AVG(LENGTH(chunk_text))::int as avg_size
                FROM document_chunks 
                WHERE unique_content_id = 100
            """)
        ).fetchone()
        
        if chunk_sizes:
            print(f"  Chunk 大小: min={chunk_sizes[0]}, max={chunk_sizes[1]}, avg={chunk_sizes[2]}")
        
        return True

def test_hybrid_search():
    """測試 hybrid search"""
    test_queries = [
        "機器學習的過擬合問題",
        "如何評估模型",
        "訓練集和驗證集"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"🧪 測試查詢: '{query}'")
        print(f"{'='*80}")
        
        try:
            results = rag_agent.search(
                user_prompt=query,
                unique_content_ids=[100],
                top_k=3
            )
            
            text_chunks = results.get("text_chunks", [])
            print(f"\n✓ 檢索到 {len(text_chunks)} 個 chunks")
            
            for i, chunk in enumerate(text_chunks, 1):
                print(f"\n--- Chunk {i} ---")
                print(f"ID: {chunk['chunk_id']}")
                print(f"來源頁面: {chunk.get('source_pages', [])}")
                print(f"相似度: {chunk.get('similarity_score', 0):.4f}")
                print(f"內容預覽 ({len(chunk['text'])} chars):")
                print(f"{chunk['text'][:200]}...")
                print(f"---")
                
        except Exception as e:
            print(f"❌ 搜索失敗: {e}")
            import traceback
            traceback.print_exc()

def main():
    print("=" * 80)
    print("測試 unique_content_id=100 的 RAG 優化效果")
    print("=" * 80)
    
    # 1. 檢查文件
    if not check_content_100():
        return
    
    # 2. 測試 hybrid search
    test_hybrid_search()
    
    print("\n" + "=" * 80)
    print("測試完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
