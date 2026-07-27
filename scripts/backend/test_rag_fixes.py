"""
驗證修復後的 BM25 分詞和相似度分數
"""
import sys
import os
sys.path.append(os.getcwd())

from backend.app.agents.rag_agent import rag_agent

def test_improvements():
    print("="*80)
    print("測試 RAG 改進：BM25 分詞 + 相似度分數修復")
    print("="*80)
    
    # 測試查詢
    query = "機器學習的過擬合問題"
    
    print(f"\n查詢: '{query}'")
    print("\n預期分詞結果: ['機器學習', '過擬合', '問題'] (停用詞 '的' 已過濾)")
    
    try:
        results = rag_agent.search(
            user_prompt=query,
            unique_content_ids=[100],
            top_k=3
        )
        
        text_chunks = results.get("text_chunks", [])
        print(f"\n✅ 檢索成功！共 {len(text_chunks)} 個 chunks\n")
        
        for i, chunk in enumerate(text_chunks, 1):
            print(f"{'='*60}")
            print(f"Chunk {i}:")
            print(f"  ID: {chunk['chunk_id']}")
            print(f"  頁面: {chunk.get('source_pages', [])}")
            print(f"  🎯 相似度分數: {chunk.get('similarity_score', 0):.4f}")
            print(f"  ({'✅ 已修復' if chunk.get('similarity_score', 0) > 0 else '❌ 仍為0'})")
            print(f"  內容預覽: {chunk['text'][:100]}...")
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_improvements()
