from typing import List, Dict, Any
import numpy as np
from backend.app.services.embedding_service import embedding_service
import logging

logger = logging.getLogger(__name__)

class SummaryCitationValidator:
    """為摘要內容歸因最相關的 chunks（使用向量搜尋）"""
    
    def __init__(self, retrieved_chunks: List[Dict]):
        self.retrieved_chunks = retrieved_chunks
        self.chunk_map = {c["chunk_id"]: c for c in retrieved_chunks}
        
        # Pre-process chunk embeddings
        self.chunk_embeddings = []
        for c in retrieved_chunks:
            emb = c.get("embedding")
            if emb is not None:
                if isinstance(emb, str):
                    emb = [float(x) for x in emb.strip('[]').split(',')]
                self.chunk_embeddings.append((c["chunk_id"], np.array(emb)))
            else:
                logger.warning(f"Chunk {c['chunk_id']} has no embedding, skipping attribution")
    
    def attribute_summary_sections(self, sections: List[Dict], top_k: int = 3, min_score: float = 0.5) -> List[Dict]:
        """
        為每個 section 歸因最相關的 chunks
        
        Args:
            sections: List of section dicts with 'content_list'
            top_k: 每個 section 返回前 k 個最相關的 chunks
        
        Returns:
            Updated sections with 'chunk_ids' and 'match_scores'
        """
        if not self.chunk_embeddings:
            logger.warning("No chunk embeddings available for attribution")
            return sections
        
        for section in sections:
            # 1. 構建查詢文本：將 content_list 串接
            content_list = section.get("content_list", [])
            query_text = " ".join(content_list)
            
            if not query_text.strip():
                continue
            
            # 2. 生成 embedding
            try:
                query_emb_list, _ = embedding_service.create_embeddings([query_text])
                query_emb = np.array(query_emb_list[0])
            except Exception as e:
                logger.error(f"Failed to generate embedding for section '{section.get('section_title')}': {e}")
                continue
            
            # 3. 計算與所有 chunks 的相似度
            scores = []
            for cid, chunk_emb in self.chunk_embeddings:
                score = self._cosine_similarity(query_emb, chunk_emb)
                # 🎯 門檻過濾
                if score >= min_score:
                    scores.append((cid, score))
            
            # 4. 取 top-k
            scores.sort(key=lambda x: x[1], reverse=True)
            top_chunks = scores[:top_k]
            
            # 5. 注入結果 (包含 chunk_ids, match_scores 和詳細 citations)
            section["chunk_ids"] = [cid for cid, _ in top_chunks]
            section["match_scores"] = [min(int(score * 100), 100) for _, score in top_chunks]
            
            citations = []
            for cid, score in top_chunks:
                chunk = self.chunk_map.get(cid, {})
                
                # Debug Log (只印一次)
                # if len(citations) == 0 and len(section["chunk_ids"]) > 0:
                #      logger.info(f"DEBUG Chunk Structure (cid={cid}): keys={list(chunk.keys())}, metadata_keys={list(chunk.get('metadata', {}).keys())}, has_source_meta={'source_metadata' in chunk}")

                # Metadata 可能在 'source_metadata' (經過 enrich) 或原始 'metadata' 中
                src_meta = chunk.get("source_metadata", {})
                raw_meta = chunk.get("metadata", {})
                source_type = chunk.get("source_type", "document") # ✅ Get source type
                
                # 1. Source Detection
                source = (
                    src_meta.get("document_name") or 
                    src_meta.get("filename") or
                    src_meta.get("file_name") or
                    raw_meta.get("file_name") or 
                    raw_meta.get("filename") or 
                    raw_meta.get("source") or 
                    "Unknown"
                )
                
                # 簡化 source 名稱，只取檔名
                if source and "/" in source:
                    source = source.split("/")[-1]
                    
                # 2. Page Detection
                # ✅ Generated content 沒有頁碼，跳過處理
                pages_list = []
                page_str = None
                start_page = 1
                
                if source_type == "document":
                    # 優先順序: 
                    # a) source_metadata.page_range (List)
                    # b) chunk.source_pages (List)
                    # c) metadata.page_numbers (List)
                    # d) Single values
                    
                    if src_meta.get("page_range"):
                        pages_list = src_meta["page_range"]
                    elif chunk.get("source_pages"):
                        pages_list = chunk.get("source_pages")
                    elif raw_meta.get("page_numbers"):
                        pages_list = raw_meta.get("page_numbers")
                    
                    page_str = "1"
                    
                    if pages_list and isinstance(pages_list, list) and len(pages_list) > 0:
                        try:
                            # Deduplicate and sort
                            valid_pages = sorted(list(set([int(p) for p in pages_list if p is not None])))
                            
                            if valid_pages:
                                start_page = valid_pages[0]
                                if len(valid_pages) > 1:
                                    # Check if sequential
                                    is_sequential = True
                                    for i in range(len(valid_pages) - 1):
                                        if valid_pages[i+1] != valid_pages[i] + 1:
                                            is_sequential = False
                                            break
                                    
                                    if is_sequential:
                                        page_str = f"{valid_pages[0]}-{valid_pages[-1]}"
                                    else:
                                        page_str = ",".join(map(str, valid_pages))
                                else:
                                    page_str = str(start_page)
                        except ValueError:
                            # Fallback if conversion fails
                            page_str = str(pages_list[0])
                    else:
                        # Fallback single value
                        val = src_meta.get("page") or raw_meta.get("page_number") or raw_meta.get("page")
                        if val:
                            page_str = str(val)
                            try:
                                start_page = int(val)
                            except:
                                pass
                
                # For compatibility with downstream logic using 'page' variable
                page = start_page
                
                # Construct complete source_metadata for frontend ReferenceDrawer
                final_source_meta = src_meta.copy() if src_meta else {}
                
                if "document_name" not in final_source_meta or not final_source_meta["document_name"]:
                    final_source_meta["document_name"] = source
                
                # ✅ Only add page info for documents, not generated content
                if source_type == "document":
                    if "page" not in final_source_meta:
                        final_source_meta["page"] = page
                        
                    # Ensure page_range is populated for Drawer to display P.6-7 correctly
                    if "page_range" not in final_source_meta or not final_source_meta["page_range"]:
                        # Try to use the list we extracted
                        if pages_list:
                             try:
                                 final_source_meta["page_range"] = sorted(list(set([int(p) for p in pages_list if p is not None])))
                             except:
                                 final_source_meta["page_range"] = [page]
                        else:
                             final_source_meta["page_range"] = [page]
                
                # Ensure other required fields for ReferenceDrawer
                if "has_images" not in final_source_meta:
                    final_source_meta["has_images"] = False
                if "uploaded_at" not in final_source_meta:
                    final_source_meta["uploaded_at"] = ""
                
                citations.append({
                    "chunk_id": cid,
                    "match_score": min(int(score * 100), 100),
                    "source": source,
                    "page_number": page_str,
                    "text": chunk.get("text", ""),
                    "source_metadata": final_source_meta
                })
            
            section["citations"] = citations
            
            # logger.info(f"Section '{section.get('section_title')}' attributed to chunks: {section['chunk_ids']}")
        
        return sections
    
    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """計算兩個向量的餘弦相似度"""
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm_v1 * norm_v2)
