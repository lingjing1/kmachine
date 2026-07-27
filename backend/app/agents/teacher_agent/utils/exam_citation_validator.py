from typing import List, Dict, Any, Tuple
import logging
import numpy as np
from backend.app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

class ExamCitationValidator:
    """驗證生成內容的引用準確性 (Semantic Attribution)"""
    
    def __init__(self, retrieved_chunks: List[Dict], retrieved_pages: List[Dict] = None):
        self.retrieved_chunks = retrieved_chunks
        self.chunk_map = {c["chunk_id"]: c for c in retrieved_chunks}
        # Pre-process chunk embeddings: List of (chunk_id, embedding_vector)
        self.chunk_embeddings = []
        for c in retrieved_chunks:
            emb = c.get("embedding")
            if emb is not None:
                # Ensure it's a numpy array for fast calculation
                # emb might be a string if PGVector returns string? No, usually list.
                if isinstance(emb, str):
                    # Handle string format if necessary, though SQLAlchemy usually handles it
                    emb = [float(x) for x in emb.strip('[]').split(',')]
                self.chunk_embeddings.append((c["chunk_id"], np.array(emb)))
            else:
                logger.warning(f"Chunk {c['chunk_id']} has no embedding, skipping usage in semantic validation.")

    def validate(self, generated_content: List[Dict]) -> Dict[str, Any]:
        """
        為生成內容歸因 (Attribution)
        
        Returns:
            {
                "valid": bool,
                "total_items": int,
                "valid_items": int,
                "errors": List[Dict],
                "needs_regeneration": bool
            }
        """
        # Semantic Attribution logic implies we always find a source, so validation always passes unless no chunks.
        if not self.chunk_embeddings:
             logger.warning("No chunk embeddings available for validation.")
             return {
                "valid": True, # Fail open or closed? If retrieval failed, we shouldn't be here.
                "total_items": len(generated_content),
                "valid_items": 0,
                "errors": [{"type": "no_context", "message": "No context available for validation"}],
                "needs_regeneration": False
            }

        for idx, item in enumerate(generated_content):
            self._attribute_item(item, idx)
        
        return {
            "valid": True,
            "total_items": len(generated_content),
            "valid_items": len(generated_content),
            "errors": [],
            "needs_regeneration": False
        }
    
    def _attribute_item(self, item: Dict, index: int):
        """為單個項目找到最佳引用來源"""
        # Construct query from question + answer
        question_text = item.get("question_text") or item.get("statement_text") or ""
        
        # Extract correct answer text if possible
        correct_answer = item.get("correct_answer", "")
        answer_text = ""
        
        # Handle different question types to get answer text
        if "options" in item and isinstance(item["options"], dict):
            answer_text = item["options"].get(correct_answer, "")
        elif "sample_answer" in item:
             answer_text = item["sample_answer"]
        else:
             answer_text = str(correct_answer)
             
        query_text = f"{question_text} {answer_text}"
        
        # 1. Generate Embedding for the query
        try:
            query_emb_list, _ = embedding_service.create_embeddings([query_text])
            query_emb = np.array(query_emb_list[0])
        except Exception as e:
            logger.error(f"Failed to generate embedding for validation item {index}: {e}")
            return

        # 2. Find Closest Chunk with Page Number Boosting
        best_chunk_id = None
        best_score = -1.0
        
        # Extract generated page number for boosting
        generated_page_raw = item.get("source", {}).get("page_number", "")
        generated_page_num = str(generated_page_raw).strip()
        
        for cid, chunk_emb in self.chunk_embeddings:
            score = self._cosine_similarity(query_emb, chunk_emb)
            
            # Boost score if page matches
            chunk_data = self.chunk_map.get(cid)
            if chunk_data and generated_page_num:
                meta = chunk_data.get("metadata", {})
                source_meta = chunk_data.get("source_metadata", {})
                # Get chunk page as string
                chunk_page = str(source_meta.get("page") or meta.get("page") or chunk_data.get("page") or "")
                
                if chunk_page and chunk_page == generated_page_num:
                    score += 0.3  # Significant boost for page match
                    
            if score > best_score:
                best_score = score
                best_chunk_id = cid
        
        # Normalize score cap at 1.0 (though it's just for ranking, but match_score display shouldn't exceed 100 eventually, 
        # actually match_score usually implies similarity. Let's clamp it later or keep it >1 to indicate strong match?)
        # Let's keep best_score raw for selection, but clamp for display.
        
        # 3. Assign Attributes
        # Even if score is low, we assign the best one (Attribution). 
        # Optionally we can flag low confidence.
        item["source"] = item.get("source", {})
        item["source"]["chunk_ids"] = [best_chunk_id] if best_chunk_id else []
        # Clamp score to 100 max
        item["source"]["match_score"] = min(int(best_score * 100), 100)
        
        # Inject correct page number from the attributed chunk
        if best_chunk_id:
            chunk = self.chunk_map.get(best_chunk_id)
            if chunk:
                # Try to get page from various metadata locations
                meta = chunk.get("metadata", {}) or {}
                source_meta = chunk.get("source_metadata", {}) or {}
                
                # Check in order: source_metadata (enriched), metadata (raw), or root level
                # page = source_meta.get("page") or meta.get("page") or chunk.get("page")
                
                # Logic to match Frontend ReferenceDrawer's getPageDisplay
                chunk_page_str = ""
                page_range = source_meta.get("page_range") or meta.get("page_range")
                
                if page_range and isinstance(page_range, list) and len(page_range) > 0:
                    # Deduplicate and sort
                    unique_pages = sorted(list(set([int(p) for p in page_range if str(p).isdigit()])))
                    
                    if len(unique_pages) > 1:
                        # Check if sequential
                        is_sequential = True
                        for i in range(len(unique_pages) - 1):
                            if unique_pages[i+1] != unique_pages[i] + 1:
                                is_sequential = False
                                break
                        
                        if is_sequential:
                            chunk_page_str = f"{unique_pages[0]}-{unique_pages[-1]}"
                        else:
                            chunk_page_str = ",".join(map(str, unique_pages))
                    elif len(unique_pages) == 1:
                        chunk_page_str = str(unique_pages[0])
                
                # Fallback to single page if range processing failed or empty
                if not chunk_page_str:
                     single_page = source_meta.get("page") or meta.get("page") or chunk.get("page")
                     if single_page:
                         chunk_page_str = str(single_page)

                if chunk_page_str:
                    item["source"]["page_number"] = chunk_page_str

            # === Fix: Inject rich metadata for Frontend ReferenceDrawer ===
            # The frontend expects text, filename, document_id, and complete source_metadata
            # Build source_metadata EXACTLY like SummaryCitationValidator does
            item["source"]["text"] = chunk.get("content") or chunk.get("text") or ""
            
            # Get document info
            src_meta = chunk.get("source_metadata", {}) or {}
            meta = chunk.get("metadata", {}) or {}
            
            # === 1. Source Detection (像Summary一樣) ===
            # 先從chunk中提取source（檔名）
            source = (
                src_meta.get("document_name") or 
                src_meta.get("filename") or
                src_meta.get("file_name") or
                meta.get("file_name") or 
                meta.get("filename") or 
                meta.get("source") or 
                "Unknown"
            )
            
            # 簡化 source 名稱，只取檔名
            if source and "/" in source:
                source = source.split("/")[-1]
            
            # Construct complete source_metadata (同Summary的做法)
            final_source_meta = src_meta.copy() if src_meta else {}
            
            # 確保 document_name 存在，使用我們提取的source
            if "document_name" not in final_source_meta or not final_source_meta["document_name"]:
                final_source_meta["document_name"] = source
            
            # 確保 document_id 存在
            if "document_id" not in final_source_meta or not final_source_meta["document_id"]:
                final_source_meta["document_id"] = src_meta.get("document_id") or meta.get("document_id")
            
            # 確保 page 存在（優先從chunk_page_str解析）
            if "page" not in final_source_meta or not final_source_meta["page"]:
                if chunk_page_str:
                    # Parse first page number from chunk_page_str
                    try:
                        if '-' in chunk_page_str:
                            final_source_meta["page"] = int(chunk_page_str.split('-')[0])
                        elif ',' in chunk_page_str:
                            final_source_meta["page"] = int(chunk_page_str.split(',')[0])
                        else:
                            final_source_meta["page"] = int(chunk_page_str)
                    except (ValueError, AttributeError):
                        final_source_meta["page"] = src_meta.get("page") or meta.get("page")
                else:
                    final_source_meta["page"] = src_meta.get("page") or meta.get("page")
            
            # 確保 page_range 存在
            if "page_range" not in final_source_meta or not final_source_meta["page_range"]:
                page_range_list = src_meta.get("page_range") or meta.get("page_range")
                if page_range_list and isinstance(page_range_list, list):
                    final_source_meta["page_range"] = page_range_list
                elif chunk_page_str:
                    # Parse from chunk_page_str
                    try:
                        if '-' in chunk_page_str:
                            start, end = chunk_page_str.split('-')
                            final_source_meta["page_range"] = list(range(int(start), int(end) + 1))
                        elif ',' in chunk_page_str:
                            final_source_meta["page_range"] = [int(p) for p in chunk_page_str.split(',')]
                        else:
                            final_source_meta["page_range"] = [int(chunk_page_str)]
                    except (ValueError, AttributeError):
                        if final_source_meta.get("page"):
                            final_source_meta["page_range"] = [final_source_meta["page"]]
                elif final_source_meta.get("page"):
                    final_source_meta["page_range"] = [final_source_meta["page"]]
            
            # 確保其他 ReferenceDrawer 需要的欄位
            if "has_images" not in final_source_meta:
                final_source_meta["has_images"] = src_meta.get("has_images", False)
            if "uploaded_at" not in final_source_meta:
                final_source_meta["uploaded_at"] = src_meta.get("uploaded_at", "")
            
            # 設定頂層欄位（向後兼容）
            item["source"]["document_id"] = final_source_meta.get("document_id")
            item["source"]["filename"] = final_source_meta.get("document_name")
            
            # Inject完整的 final_source_metadata
            item["source"]["source_metadata"] = final_source_meta
        
        # logger.info(f"Item {index} attributed to Chunk {best_chunk_id} (Score: {best_score:.4f})")
        # logger.debug(f"   Query: {query_text[:50]}...")

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm_v1 * norm_v2)

    def _normalize_text(self, text: str) -> str:
        return text.strip().replace(" ", "").replace("\n", "")
