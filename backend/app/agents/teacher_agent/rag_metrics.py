"""
RAG 檢索指標計算工具
"""
import re

def calculate_rag_metrics(log_data: dict) -> dict:
    """
    計算 RAG 檢索指標
    """
    metrics = {}
    
    # 1. 關鍵字覆蓋率 (Keyword Coverage)
    if log_data.get("selected_kps") and log_data.get("final_chunks"):
        kps = log_data["selected_kps"]
        chunks_text = " ".join([c.get("text", "") for c in log_data["final_chunks"]])
        
        hits = {}
        for kp in kps:
            # 支援「中文 (English)」格式的模糊匹配
            # 只要全文中出現中文部分、英文部分，或完整的 KP 名稱，皆視為命中
            if kp in chunks_text:
                hits[kp] = 1
                continue
            
            # 嘗試拆分 中文 與 英文 (English)
            match = re.match(r'^(.+?)\s*\((.+?)\)$', kp)
            if match:
                zh_part = match.group(1).strip()
                en_part = match.group(2).strip()
                if (zh_part and zh_part in chunks_text) or (en_part and en_part in chunks_text):
                    hits[kp] = 1
                    continue
            
            # 預設未命中
            hits[kp] = 0
        
        coverage = sum(hits.values()) / len(kps) if kps else 0
        metrics["keyword_coverage"] = coverage
        metrics["keyword_hits"] = hits
    else:
        metrics["keyword_coverage"] = 0.0
        metrics["keyword_hits"] = {}
    
    # 2. Vector Score 分析
    vector_results = log_data.get("vector_results", [])
    if vector_results:
        scores = [r.get("score", 0) for r in vector_results]
        metrics["avg_vector_score"] = sum(scores) / len(scores)
        metrics["top1_vector_score"] = scores[0] if scores else 0
    else:
        metrics["avg_vector_score"] = 0.0
        metrics["top1_vector_score"] = 0.0
    
    # 3. BM25 命中數
    bm25_results = log_data.get("bm25_results", [])
    metrics["bm25_hit_count"] = len(bm25_results)
    
    # 4. RRF 最高分
    final_chunks = log_data.get("final_chunks", [])
    metrics["rrf_top_score"] = final_chunks[0].get("rrf_score", 0) if final_chunks else 0
    
    # 5. 多樣性
    metrics["diversity_chunks"] = len(final_chunks)
    
    unique_pages = set()
    for chunk in final_chunks:
        pages = chunk.get("pages", [])
        unique_pages.update(pages)
    metrics["diversity_pages"] = len(unique_pages) if unique_pages else None
    
    # 6. 品質評估
    quality = "需改進"
    # 若命中率高且向量分數尚可，或向量分數極高，視為良好
    is_good_coverage = metrics["keyword_coverage"] > 0.6
    is_good_vector = metrics["top1_vector_score"] > 0.6
    
    if is_good_coverage and is_good_vector and metrics["bm25_hit_count"] >= 2:
        quality = "優秀"
    elif is_good_coverage or is_good_vector:
        quality = "良好"
    
    metrics["quality_assessment"] = quality
    
    return metrics


def auto_evaluate_rag_results(
    original_query: str,
    enhanced_query: str,
    selected_kps: list,
    vector_results: list,
    bm25_results: list,
    final_chunks: list
):
    """
    自動評估 RAG 檢索結果（從 RAG Agent 調用）
    """
    log_data = {
        "enhanced_query": enhanced_query,
        "original_query": original_query,
        "selected_kps": selected_kps,
        "vector_results": vector_results,
        "bm25_results": bm25_results,
        "final_chunks": final_chunks
    }
    
    return calculate_rag_metrics(log_data)
