
import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import text, Table, select
from pgvector.sqlalchemy import Vector

logger = logging.getLogger(__name__)

from backend.app.services.embedding_service import embedding_service
from backend.app.config.settings import settings
from backend.app.db import engine, metadata
from backend.app.utils.time_utils import get_now_taipei

# --- Database Setup ---
# Using shared engine and metadata from backend.app.db

# Reflect existing tables
document_chunks = Table('document_chunks', metadata, autoload_with=engine)
document_content = Table('document_content', metadata, autoload_with=engine)
document_knowledge_points = Table('document_knowledge_points', metadata, autoload_with=engine)
generated_content_chunks = Table('generated_content_chunks', metadata, autoload_with=engine)


class RAGAgent:
    """
    Agent for performing Retrieval-Augmented Generation tasks.
    This class handles all RAG-related logic.
    """
    def __init__(self):
        from backend.app.services.bm25_service import BM25Service
        self.bm25 = BM25Service()
        self._load_dynamic_dictionary()

    def _load_dynamic_dictionary(self):
        """Load all KP names into Jieba dictionary to prevents over-segmentation"""
        try:
            stmt = select(document_knowledge_points.c.knowledge_point_name)
            with engine.connect() as conn:
                results = conn.execute(stmt).fetchall()
                kp_names = [row[0] for row in results if row[0]]
            
            if kp_names:
                # 智能拆分：若名稱包含「中文 (English)」，將兩者分開加入辭典，避免長難句分詞失敗
                terms_to_add = set()
                import re
                for name in kp_names:
                    terms_to_add.add(name)
                    match = re.match(r'^(.+?)\s*\((.+?)\)$', name)
                    if match:
                        terms_to_add.add(match.group(1).strip())
                        terms_to_add.add(match.group(2).strip())
                
                self.bm25.add_terms(list(terms_to_add))
                current_time = get_now_taipei().strftime("%H:%M:%S")
                print(f"[COOK-AI] {current_time} - ✓ RAGAgent: Loaded {len(terms_to_add)} KP terms (expanded from {len(kp_names)}) into dictionary.")

        except Exception as e:
            print(f"⚠️ Failed to load dynamic dictionary: {e}")
            
    def _get_kp_descriptions(self, kp_names: List[str]) -> Dict[str, str]:
        """Fetch descriptions for given KP names"""
        if not kp_names:
            return {}
            
        stmt = select(document_knowledge_points.c.knowledge_point_name, document_knowledge_points.c.kp_description).where(
            document_knowledge_points.c.knowledge_point_name.in_(kp_names)
        )
        
        with engine.connect() as conn:
            results = conn.execute(stmt).fetchall()
            
        return {row.knowledge_point_name: row.kp_description for row in results}

    def search(
        self, 
        user_prompt: str, 
        unique_content_ids: List[int], 
        top_k: Optional[int] = None, 
        selected_kp_names: Optional[List[str]] = None,
        generated_course_content_ids: Optional[List[int]] = None,
        unit_id: Optional[int] = None,
        ablation_group: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Performs RAG search. Dispatches to hybrid_search or vector_search based on settings.
        Supports Separated Retrieval: BM25 (KP Keywords) + Vector (Semantic Prompt).
        
        Args:
            user_prompt: User query
            unique_content_ids: List of source IDs for uploaded documents
            top_k: Number of results to return
            selected_kp_names: KPs for enhancement
            generated_course_content_ids: List of course_content_ids for generated content sources
            unit_id: Optional unit ID to automatically include all saved course contents
            ablation_group: The experimental group (e.g., 'naive-rag', 'hybrid-rag', 'kp-hybrid-rag')
        """
        if top_k is None:
            top_k = settings.rag.top_k
        
        # Ensure lists
        if isinstance(unique_content_ids, int):
            unique_content_ids = [unique_content_ids]
        if generated_course_content_ids is None:
            generated_course_content_ids = []
        if isinstance(generated_course_content_ids, int):
            generated_course_content_ids = [generated_course_content_ids]
            
        # ✅ Automatically include all saved course contents for this unit
        auto_included_gen_ids = []
        if unit_id and not ablation_group:
            try:
                with engine.connect() as conn:
                    # We need the course_contents.id because generated_content_chunks.course_content_id maps to it
                    stmt = text("SELECT id FROM course_contents WHERE unit_id = :uid AND source_type = 'generated_content'")
                    rows = conn.execute(stmt, {"uid": unit_id}).fetchall()
                    saved_ids = [row[0] for row in rows if row[0]]
                    if saved_ids:
                        auto_included_gen_ids = [sid for sid in saved_ids if sid not in generated_course_content_ids]
                        generated_course_content_ids = list(set(generated_course_content_ids + auto_included_gen_ids))
                        logger.info(f"Unit {unit_id}: Automatically included {len(auto_included_gen_ids)} saved course contents for repetition avoidance.")
            except Exception as e:
                logger.error(f"Failed to auto-include unit contents: {e}")
            
        if selected_kp_names:
            logger.info(f"Target Documents: {unique_content_ids}, Generated: {generated_course_content_ids}")
            logger.info(f"Selected KP Names: {selected_kp_names}")
        
        if not unique_content_ids and not generated_course_content_ids:
            return {"text_chunks": [], "page_content": []}

        is_naive_rag = ablation_group == 'naive-rag'
        is_hybrid_rag = ablation_group in ['hybrid-rag', 'kp-hybrid-rag']
        
        # Override settings based on ablation_group if provided
        use_hybrid = is_hybrid_rag if ablation_group else settings.rag.use_hybrid_search

        if use_hybrid:
            return self.hybrid_search(
                user_prompt, 
                unique_content_ids, 
                generated_course_content_ids,
                top_k, 
                selected_kp_names=selected_kp_names,
                ablation_group=ablation_group,
                auto_included_gen_ids=auto_included_gen_ids
            )
        else:
            return self._vector_search_flow(
                user_prompt, 
                unique_content_ids, 
                generated_course_content_ids, 
                top_k,
                selected_kp_names=selected_kp_names,
                ablation_group=ablation_group,
                auto_included_gen_ids=auto_included_gen_ids
            )

    def hybrid_search(
        self,
        user_prompt: str,
        unique_content_ids: List[int],
        generated_course_content_ids: List[int],
        top_k: int = 10,
        alpha: float = 0.6,  # Vector weight
        selected_kp_names: Optional[List[str]] = None,
        ablation_group: Optional[str] = None,
        auto_included_gen_ids: Optional[List[int]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Hybrid search: Vector (α) + BM25 (1-α) with RRF fusion.
        Strategy: Separated Retrieval (Prompt for Vector, KPs for BM25)
        """
        # logger.info(f"🔬 HYBRID SEARCH (α={alpha}, Top-K={top_k})")
        
        # Step 1: Vector Search (Use Semantic Prompt + KP Enhancement)
        # ✅ KP Query Enhancement (Phase 3 Optimization)
        vector_query = user_prompt
        # Group B ('hybrid-rag') explicitly disables KP Query Enhancement for ablation study
        should_enhance_query = settings.rag.enable_kp_query_enhancement and selected_kp_names and ablation_group != 'hybrid-rag'
        
        if should_enhance_query:
            from backend.app.agents.teacher_agent.utils.kp_query_enhancer import KPQueryEnhancer
            vector_query = KPQueryEnhancer.enhance(user_prompt, selected_kp_names)
            logger.info(f"Enhanced Prompt: {vector_query[:100]}...")
        
        vector_results = self._fetch_vector_candidates(vector_query, unique_content_ids, generated_course_content_ids, top_k * 2)
        # Suppressed verbose prints for cleaner logs
        # Top-1 vector result: chunk_id={vector_results[0]['chunk_id']}, score={vector_results[0]['similarity_score']:.4f} if vector_results else None
        
        # DEBUG prints for chunks are now removed as requested
        pass
        
        
        # Step 2: BM25 Search (Use Precise Keywords)
        print(f"\n📊 Step 2: BM25 Keywork Search")
        
        # Determine BM25 Query
        if selected_kp_names:
            # ✅ Separated Strategy: Use KP names + English Terms from Description as keywords
            kp_descriptions = self._get_kp_descriptions(selected_kp_names)
            
            search_terms = []
            for kp in selected_kp_names:
                search_terms.append(kp)
                # Try to extract en_name from description
                # Format: "en_name: Machine Learning. ..."
                desc = kp_descriptions.get(kp, "")
                if desc and "en_name:" in desc:
                    try:
                        # Extract content between "en_name:" and the first period
                        en_name_part = desc.split("en_name:", 1)[1]
                        en_term = en_name_part.split(".", 1)[0].strip()
                        if en_term:
                            search_terms.append(en_term)
                    except Exception:
                        pass # Ignore parsing errors
            
            bm25_query = " ".join(search_terms)
            logger.info(f"BM25 Query: {bm25_query[:100]}...")
        else:
            # Fallback: Use original prompt
            bm25_query = user_prompt
            logger.info(f"BM25 Query (fallback): {bm25_query[:100]}...")

        eligible_chunks = self._get_chunks_for_bm25(unique_content_ids, generated_course_content_ids)
        self.bm25.build_index(eligible_chunks)
        
        bm25_results = self.bm25.search(bm25_query, top_k * 2)
        # Suppressed verbose prints for cleaner logs
        
        # DEBUG prints for BM25 chunks removal
        pass
        
        
        # Step 3: Reciprocal Rank Fusion
        # Step 3: Reciprocal Rank Fusion
        fused_results = self._reciprocal_rank_fusion(
            vector_results, 
            bm25_results, 
            alpha=alpha,
            k=60
        )
        # Suppressed RRF ranking logs for brevity
        pass
        
        # Step 4: Fetch full content for top_k fused results
        # Step 4: Fetch full content for top_k fused results
        top_chunk_ids = [r["chunk_id"] for r in fused_results[:top_k]]
        logger.info(f"Top {top_k} RAG chunks selected for context.")
        
        # Preserve fused scores by passing them along
        fused_score_map = {r["chunk_id"]: r["fused_score"] for r in fused_results}
        
        # 獲取最終結果（只調用一次）
        final_result = self._fetch_full_response_by_ids(
            top_chunk_ids, 
            fused_score_map=fused_score_map,
            pre_fetched_chunks=vector_results, # ✅ Reuse pre-fetched chunks to ensure embeddings are present
            auto_included_gen_ids=auto_included_gen_ids
        )
        
        # DEBUG prints for Final chunks removal
        pass
        

        # Calculate metrics using unified method
        rag_metrics = self._calculate_metrics(
            user_prompt=user_prompt,
            vector_query=vector_query,
            selected_kp_names=selected_kp_names,
            vector_results=vector_results,
            bm25_results=bm25_results,
            final_result=final_result
        )
        
        final_result["rag_metrics"] = rag_metrics
        return final_result

    def _calculate_metrics(
        self,
        user_prompt: str,
        vector_query: str,
        selected_kp_names: Optional[List[str]],
        vector_results: List[Dict],
        bm25_results: List[Tuple],
        final_result: Dict
    ) -> Dict:
        """Unified RAG metrics calculation"""
        if not settings.rag.enable_rag_auto_evaluation:
            return {}
            
        try:
            from backend.app.agents.teacher_agent.rag_metrics import auto_evaluate_rag_results
            
            # Prepare data for evaluation
            vector_results_for_eval = [{"chunk_id": r["chunk_id"], "score": r.get("similarity_score", 0), "text": r.get("text", "")} for r in vector_results]
            bm25_results_for_eval = [{"chunk_id": cid, "score": score} for cid, score in bm25_results]
            # For hybrid search, bm25_results is populated. If not populated, it's pure vector search (e.g. naive-rag)
            is_hybrid = len(bm25_results) > 0
            final_chunks_for_eval = [
                {
                    "chunk_id": chunk["chunk_id"], 
                    "rrf_score": chunk.get("similarity_score", 0.0) if is_hybrid else 0.0, 
                    "pages": chunk.get("source_pages", []), 
                    "text": chunk.get("text", "")
                } for chunk in final_result.get("text_chunks", [])
            ]
            
            return auto_evaluate_rag_results(
                original_query=user_prompt,
                enhanced_query=vector_query,
                selected_kps=selected_kp_names or [],
                vector_results=vector_results_for_eval,
                bm25_results=bm25_results_for_eval,
                final_chunks=final_chunks_for_eval
            )
        except Exception as e:
            logger.error(f"RAG Metrics evaluation failed: {e}")
            return {}

    def _vector_search_flow(
        self, 
        user_prompt: str, 
        unique_content_ids: List[int], 
        generated_course_content_ids: List[int],
        top_k: int,
        selected_kp_names: Optional[List[str]] = None,
        ablation_group: Optional[str] = None,
        auto_included_gen_ids: Optional[List[int]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Pure vector search flow with metrics support
        """
        vector_results = self._fetch_vector_candidates(user_prompt, unique_content_ids, generated_course_content_ids, top_k)
        chunk_ids = [r["chunk_id"] for r in vector_results]
        final_result = self._fetch_full_response_by_ids(
            chunk_ids, 
            pre_fetched_chunks=vector_results,
            auto_included_gen_ids=auto_included_gen_ids
        )
        
        # Calculate metrics for vector flow
        rag_metrics = self._calculate_metrics(
            user_prompt=user_prompt,
            vector_query=user_prompt,
            selected_kp_names=selected_kp_names,
            vector_results=vector_results,
            bm25_results=[], # No BM25 in pure vector flow
            final_result=final_result
        )
        final_result["rag_metrics"] = rag_metrics
        return final_result

    def _fetch_vector_candidates(
        self, 
        user_prompt: str, 
        unique_content_ids: List[int], 
        generated_course_content_ids: List[int],
        limit: int
    ) -> List[Dict]:
        """Performs pure vector search across both tables and returns lightweight chunk objects with prefixed IDs"""
        logger.info(f"🔍 RAG: Fetching top {limit} vector candidates for ranking...")
        query_embedding = embedding_service.create_embeddings([user_prompt])[0][0]
        
        results = []
        
        with engine.connect() as conn:
            # 1. Search Document Chunks
            if unique_content_ids:
                stmt_docs = text(f"""
                    SELECT id, chunk_text, metadata, multimodal_metadata,
                        1 - (embedding <=> :query_embedding) AS similarity_score,
                        unique_content_id, embedding
                    FROM {document_chunks.name}
                    WHERE unique_content_id IN :unique_content_ids
                    ORDER BY embedding <=> :query_embedding
                    LIMIT :limit
                """)
                
                doc_results = conn.execute(
                    stmt_docs,
                    {
                        "query_embedding": str(query_embedding), 
                        "unique_content_ids": tuple(unique_content_ids), 
                        "limit": limit
                    }
                ).fetchall()
                
                for row in doc_results:
                    results.append({
                        "chunk_id": f"doc_{row.id}",
                        "text": row.chunk_text,
                        "metadata": row.metadata,
                        "multimodal_metadata": row.multimodal_metadata,
                        "similarity_score": float(row.similarity_score),
                        "unique_content_id": row.unique_content_id,
                        "embedding": row.embedding,
                        "source_type": "document"
                    })

            # 2. Search Generated Content Chunks
            if generated_course_content_ids:
                stmt_gen = text(f"""
                    SELECT id, chunk_text, metadata, multimodal_metadata,
                        1 - (embedding <=> :query_embedding) AS similarity_score,
                        course_content_id, embedding
                    FROM {generated_content_chunks.name}
                    WHERE course_content_id IN :course_content_ids
                    ORDER BY embedding <=> :query_embedding
                    LIMIT :limit
                """)
                
                gen_results = conn.execute(
                    stmt_gen,
                    {
                        "query_embedding": str(query_embedding),
                        "course_content_ids": tuple(generated_course_content_ids),
                        "limit": limit
                    }
                ).fetchall()
                
                for row in gen_results:
                    results.append({
                        "chunk_id": f"gen_{row.id}",
                        "text": row.chunk_text,
                        "metadata": row.metadata,
                        "multimodal_metadata": row.multimodal_metadata,
                        "similarity_score": float(row.similarity_score),
                        "course_content_id": row.course_content_id,
                        "embedding": row.embedding,
                        "source_type": "generated"
                    })

        # Sort combined results by similarity score descending and take top limit
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:limit]

    def _get_chunks_for_bm25(self, unique_content_ids: List[int], generated_course_content_ids: List[int]) -> List[Dict]:
        """Fetches all chunks for the given documents/generated content for BM25 indexing"""
        all_chunks = []
        
        with engine.connect() as conn:
            # 1. Document Chunks
            if unique_content_ids:
                stmt_doc = text(f"""
                    SELECT id, chunk_text, metadata
                    FROM {document_chunks.name}
                    WHERE unique_content_id IN :unique_content_ids
                """)
                rows = conn.execute(stmt_doc, {"unique_content_ids": tuple(unique_content_ids)}).fetchall()
                all_chunks.extend([
                    {"chunk_id": f"doc_{row.id}", "text": row.chunk_text, "metadata": row.metadata} 
                    for row in rows
                ])
                
            # 2. Generated Content Chunks
            if generated_course_content_ids:
                stmt_gen = text(f"""
                    SELECT id, chunk_text, metadata
                    FROM {generated_content_chunks.name}
                    WHERE course_content_id IN :course_content_ids
                """)
                rows = conn.execute(stmt_gen, {"course_content_ids": tuple(generated_course_content_ids)}).fetchall()
                all_chunks.extend([
                    {"chunk_id": f"gen_{row.id}", "text": row.chunk_text, "metadata": row.metadata}
                    for row in rows
                ])
            
        return all_chunks

    def _reciprocal_rank_fusion(
        self, 
        vector_results: List[Dict], 
        bm25_results: List[Tuple[Any, float]], # Chunk ID can be string now
        alpha: float,
        k: int = 60
    ) -> List[Dict]:
        """
        RRF Formula: score(d) = α * (1/(k+rank_vec)) + (1-α) * (1/(k+rank_bm25))
        """
        scores = {}
        
        # Vector ranks
        for rank, chunk in enumerate(vector_results):
            cid = chunk["chunk_id"]
            scores[cid] = alpha / (k + rank + 1)
        
        # BM25 ranks
        for rank, (cid, bm25_score) in enumerate(bm25_results):
            if cid in scores:
                scores[cid] += (1 - alpha) / (k + rank + 1)
            else:
                scores[cid] = (1 - alpha) / (k + rank + 1)
        
        # Sort by fused score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"chunk_id": cid, "fused_score": score} for cid, score in ranked]

    def _fetch_full_response_by_ids(
        self, 
        chunk_ids: List[str], 
        pre_fetched_chunks: List[Dict] = None, 
        fused_score_map: Dict[str, float] = None,
        auto_included_gen_ids: Optional[List[int]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Re-fetches full details for selected chunk IDs and retrieves corresponding page content.
        Uses pre_fetched_chunks to avoid DB re-fetch if available.
        fused_score_map: Optional mapping of chunk_id -> fused_score for hybrid search
        """
        # 0. Extract source types and names early for categorization
        # gen_chunk_ids are IDs in generated_content_chunks
        # gen_source_ids are IDs in generated_contents/course_contents
        gen_chunk_ids = {int(cid[4:]) for cid in chunk_ids if cid.startswith("gen_")}
        gen_source_ids = set() # To be populated during processing
        doc_id_to_name = {}

        if not chunk_ids:
            return {"text_chunks": [], "page_content": []}
            
        ordered_chunks = []
        
        # 1. Get Text Chunks
        if pre_fetched_chunks:
             # Fast path: use pre-fetched data
             chunk_map = {c["chunk_id"]: c for c in pre_fetched_chunks}
             ordered_chunks = [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]
             # Populate doc_id_to_name from pre-fetched chunks
             for c in ordered_chunks:
                 doc_id = c.get("unique_content_id") or c.get("course_content_id")
                 doc_name = c.get("metadata", {}).get("document_name")
                 if doc_id and doc_name:
                     doc_id_to_name[doc_id] = doc_name
        else:
            # Re-fetch from DB based on ID prefix
            doc_chunk_id_set = {int(cid[4:]) for cid in chunk_ids if cid.startswith("doc_")}
            doc_ids = list(doc_chunk_id_set)
            gen_ids = list(gen_chunk_ids)
            
            fetched_results = {}
            # doc_id_to_name will be populated inside _fetch_documents_and_generated_contents
            
            with engine.connect() as conn:
                if doc_ids:
                    stmt = text(f"""
                        SELECT id, chunk_text, metadata, multimodal_metadata, unique_content_id, embedding
                        FROM {document_chunks.name}
                        WHERE id IN :ids
                    """)
                    rows = conn.execute(stmt, {"ids": tuple(doc_ids)}).fetchall()
                    for row in rows:
                        full_id = f"doc_{row.id}"
                        fetched_results[full_id] = {
                            "chunk_id": full_id,
                            "text": row.chunk_text,
                            "metadata": row.metadata,
                            "multimodal_metadata": row.multimodal_metadata,
                            "unique_content_id": row.unique_content_id,
                            "embedding": row.embedding,
                            "source_type": "document"
                        }
                        
                if gen_ids:
                    stmt = text(f"""
                        SELECT id, chunk_text, metadata, multimodal_metadata, course_content_id, embedding
                        FROM {generated_content_chunks.name}
                        WHERE id IN :ids
                    """)
                    rows = conn.execute(stmt, {"ids": tuple(gen_ids)}).fetchall()
                    for row in rows:
                        full_id = f"gen_{row.id}"
                        fetched_results[full_id] = {
                            "chunk_id": full_id,
                            "text": row.chunk_text,
                            "metadata": row.metadata,
                            "multimodal_metadata": row.multimodal_metadata,
                            "course_content_id": row.course_content_id,
                            "embedding": row.embedding,
                            "source_type": "generated"
                        }

            # Order them
            ordered_chunks = [fetched_results[cid] for cid in chunk_ids if cid in fetched_results]

        # 2. Process for Return & Formatting
        final_text_chunks = []
        doc_pages_to_retrieve: Dict[int, set] = {}
        # Track generated content chunks by their source ID (course_content_id)
        gen_content_by_source: Dict[int, List[Dict]] = {}

        if auto_included_gen_ids is None:
            auto_included_gen_ids = []

        for chunk in ordered_chunks:
            meta = chunk["metadata"].copy() if chunk["metadata"] else {}
            mm_meta = chunk.get("multimodal_metadata") or {}
            
            # Combine image info
            images = meta.get("images", []) or mm_meta.get("images", [])
            page_numbers = meta.get("page_numbers", [])
            
            # Extract basic info
            doc_id = chunk.get("unique_content_id") or chunk.get("course_content_id")
            doc_name = meta.get("document_name", "Unknown Document")
            uploaded_at = meta.get("uploaded_at", "")
            doc_id_to_name[doc_id] = doc_name

            if chunk.get("source_type") == "document" and doc_id:
                if doc_id not in doc_pages_to_retrieve:
                    doc_pages_to_retrieve[doc_id] = set()
                doc_pages_to_retrieve[doc_id].update(page_numbers)
            elif chunk.get("source_type") == "generated" and doc_id:
                gen_source_ids.add(doc_id)
                if doc_id not in gen_content_by_source:
                    gen_content_by_source[doc_id] = []
                gen_content_by_source[doc_id].append(chunk)

            # --- KEY FIX: Ignore auto-included chunks for final_text_chunks (citations) ---
            if doc_id in auto_included_gen_ids:
                continue
            
            # Get score
            score = chunk.get("similarity_score", 0.0)
            if fused_score_map and chunk["chunk_id"] in fused_score_map:
                score = fused_score_map[chunk["chunk_id"]]

            # Format images for frontend (map image_path to url)
            formatted_images = []
            for img in images[:3]:
                img_copy = img.copy()
                if "image_path" in img_copy and "url" not in img_copy:
                    img_copy["url"] = f"/uploads/{img_copy['image_path']}"
                formatted_images.append(img_copy)

            # Standardized source_metadata for frontend ReferenceDrawer
            source_metadata_formatted = {
                "document_id": doc_id,
                "document_name": doc_name,
                "uploaded_at": uploaded_at,
                "page": page_numbers[0] if page_numbers else meta.get("page"),
                "page_range": page_numbers,
                "has_images": len(formatted_images) > 0,
                "images": formatted_images,
                "similarity_score": round(score, 4),
                "chunk_order": chunk.get("chunk_order")
            }

            final_text_chunks.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "source_type": chunk.get("source_type"),
                "source_id": doc_id,
                "source_pages": page_numbers,
                "similarity_score": round(score, 4),
                "multimodal_metadata": mm_meta,
                "source_metadata": source_metadata_formatted,
                "embedding": chunk.get("embedding")
            })

        # 3. Retrieve & Enrich Page Content
        found_page_content = []
        
        for content_id, page_nums in doc_pages_to_retrieve.items():
            if not page_nums:
                continue
            
            page_numbers_str = ", ".join(map(str, page_nums))
            content_stmt = text(f"""
                SELECT page_number, structured_content, combined_human_text
                FROM {document_content.name}
                WHERE unique_content_id = :unique_content_id AND page_number IN ({page_numbers_str})
                ORDER BY page_number
            """)
            
            with engine.connect() as conn:
                retrieved_pages = conn.execute(content_stmt, {"unique_content_id": content_id}).fetchall()

            doc_name = doc_id_to_name.get(content_id, "Unknown Document")
            
            # Determine if this content_id was from generated documents or original uploads
            source_category = "existing_material" if content_id in auto_included_gen_ids else "original_document"

            for page in retrieved_pages:
                page_num, structured_data, human_text = page
                
                # Ensure images in structured_data have URLs
                if isinstance(structured_data, list):
                    for elem in structured_data:
                        if elem.get("type") == "image":
                            img_path = elem.get("image_path")
                            if img_path and not elem.get("url"):
                                elem["url"] = f"/api/uploads/{img_path}"

                found_page_content.append({
                    "type": "structured_page_content",
                    "source_category": source_category,
                    "source_document_id": content_id,
                    "document_name": doc_name,
                    "page_number": page_num,
                    "content": structured_data,
                    "combined_human_text": human_text
                })

        # 4. Enrich Page Content with Generated Material (Treat as virtual pages)
        for source_id, chunks in gen_content_by_source.items():
            doc_name = doc_id_to_name.get(source_id, "Generated Material")
            
            # Combine all chunks from the same source into one "page" for the LLM
            combined_text = "\n\n".join([c["text"] for c in chunks])
            
            # Find images if any
            all_images = []
            for c in chunks:
                raw_meta = c.get("metadata") or {}
                raw_mm = c.get("multimodal_metadata") or {}
                imgs = raw_meta.get("images", []) or raw_mm.get("images", [])
                for img in imgs:
                    if "image_path" in img:
                        img_copy = img.copy()
                        if not img_copy.get("url"):
                            img_copy["url"] = f"/api/uploads/{img_copy['image_path']}"
                        all_images.append(img_copy)

            source_category = "existing_material" if source_id in auto_included_gen_ids else "original_document"
            found_page_content.append({
                "type": "structured_page_content",
                "source_category": source_category,
                "source_document_id": source_id,
                "document_name": doc_name,
                "page_number": 1, 
                "content": [{"type": "text", "content": combined_text}] + all_images,
                "combined_human_text": combined_text
            })

        return {
            "text_chunks": final_text_chunks,
            "page_content": found_page_content
        }


# Singleton instance for easy access
rag_agent = RAGAgent()

if __name__ == '__main__':
    # Example usage:
    # Ensure you have run the ingestion_orchestrator first to populate data
    # from app.agents.ingestion_orchestrator import process_file
    # process_file(file_path="test_files/sample2.pdf", uploader_id=1, course_id=1, force_reprocess=True)
    
    # Mock a unique_content_id that exists in your DB after ingestion
    # You might need to manually find an ID from your 'unique_contents' table
    MOCK_UNIQUE_CONTENT_IDS = [1] # Replace with actual IDs
    
    test_prompt = "What is the role of a Principal Investigator in clinical trials?"
    
    if MOCK_UNIQUE_CONTENT_IDS:
        search_result = rag_agent.search(test_prompt, MOCK_UNIQUE_CONTENT_IDS)
        
        import json
        print("\n--- RAGAgent Search Result ---")
        print(json.dumps(search_result, indent=2, ensure_ascii=False))
        print("-----------------------------\n")
    else:
        print("Skipping RAGAgent test.")
