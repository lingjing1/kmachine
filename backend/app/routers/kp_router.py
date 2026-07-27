"""
KP (Knowledge Point) Extraction Router

Provides on-demand KP extraction API for Generator Settings workflow.
Teachers trigger extraction after document ingestion and preview.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, insert, text
import json
import time

from backend.app.config.settings import settings
from backend.app.services.kp_extractor import extract_knowledge_points, extract_document_summary
from backend.app.utils import db_logger
from backend.app.db import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.time_utils import get_now_taipei

# Create router
router = APIRouter(prefix="/api/kp", tags=["Knowledge Point Extraction"])


# --- Pydantic Models ---

class KPExtractionRequest(BaseModel):
    """Request model for KP extraction."""
    unique_content_id: int = Field(..., description="Document ID to extract KPs from")
    teacher_id: int = Field(..., description="Teacher ID who triggered extraction")
    force_regenerate: bool = Field(False, description="Force regenerate even if KPs exist")


class KPExtractionResponse(BaseModel):
    """Response model for KP extraction."""
    status: str
    message: str
    kp_map: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class KPRetrievalResponse(BaseModel):
    """Response model for retrieving existing KPs."""
    unique_content_id: int
    teacher_id: int

    version: int
    kp_map: Dict[str, Any]


# --- Helper Functions ---

def _sync_get_document_pages(unique_content_id: int):
    with engine.connect() as conn:
        # Get file name and content
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
            WHERE uc.id = :unique_content_id
            ORDER BY dc.page_number
        """), {"unique_content_id": unique_content_id})
        
        rows = result.fetchall()
        
        if not rows:
            return None, "not_found"
        
        file_name = rows[0][2] or "未知檔案"
        
        # Assemble pages
        pages = []
        for row in rows:
            if row[3]:  # combined_human_text exists
                pages.append({
                    'text': row[3],
                    'page_number': row[4],
                    'metadata': {}
                })
        
        if not pages:
            return None, "no_content"
        
        return (file_name, pages), None

async def _get_document_pages(unique_content_id: int) -> tuple[str, List[Dict]]:
    """
    Retrieve document pages and metadata from database.
    
    Returns:
        (file_name, pages) where pages is list of dicts with 'text', 'page_number', 'metadata'
    """
    result, error = await run_in_db_pool(_sync_get_document_pages, unique_content_id)
    
    if error == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Document with unique_content_id={unique_content_id} not found"
        )
    elif error == "no_content":
        raise HTTPException(
            status_code=400,
            detail=f"Document {unique_content_id} has no extractable content"
        )
        
    return result


def _save_kp_to_database(
    unique_content_id: int,
    teacher_id: int,
    kp_result: Dict[str, Any],
    job_id: int
) -> int:
    """
    Save extracted KP map to database.
    
    Returns:
        version number of the saved KP map
    """
    with engine.connect() as conn:
        with conn.begin():
            # Step 1: Deactivate previous versions for this (content_id, teacher_id)
            conn.execute(text("""
                UPDATE document_knowledge_points
                SET is_active = false
                WHERE unique_content_id = :content_id 
                AND teacher_id = :teacher_id
            """), {"content_id": unique_content_id, "teacher_id": teacher_id})
            
            # Step 2: Determine new version number
            version_result = conn.execute(text("""
                SELECT COALESCE(MAX(version), 0) + 1
                FROM document_knowledge_points
                WHERE unique_content_id = :content_id 
                AND teacher_id = :teacher_id
            """), {"content_id": unique_content_id, "teacher_id": teacher_id})
            
            new_version = version_result.scalar()
            
            # Step 3: Insert knowledge points
            kp_id_mapping = {}  # Map mermaid_id to database id
            
            for kp in kp_result['knowledge_points']:
                insert_result = conn.execute(text("""
                    INSERT INTO document_knowledge_points (
                        unique_content_id, teacher_id, version,
                        knowledge_point_name, kp_description, kp_level,
                        parent_kp_id, confidence_score, mermaid_node_id,
                        is_active, extracted_at, modified_at
                    ) VALUES (
                        :unique_content_id, :teacher_id, :version,
                        :name, :description, :level,
                        NULL, :confidence, :mermaid_id,
                        true, :now, :now
                    )
                    RETURNING id
                """), {
                    "unique_content_id": unique_content_id,
                    "teacher_id": teacher_id,
                    "version": new_version,
                    "name": kp['name'],
                    "description": kp.get('description'),
                    "level": kp.get('level'),
                    "confidence": kp.get('confidence', 0),
                    "mermaid_id": kp['mermaid_id'],
                    "now": get_now_taipei()
                })
                
                db_id = insert_result.scalar()
                kp_id_mapping[kp['mermaid_id']] = db_id
            
            # Step 4: Update parent_kp_id based on parent_mermaid_id
            for kp in kp_result['knowledge_points']:
                parent_mermaid_id = kp.get('parent_mermaid_id')
                if parent_mermaid_id and parent_mermaid_id in kp_id_mapping:
                    conn.execute(text("""
                        UPDATE document_knowledge_points
                        SET parent_kp_id = :parent_id
                        WHERE id = :kp_id
                    """), {
                        "parent_id": kp_id_mapping[parent_mermaid_id],
                        "kp_id": kp_id_mapping[kp['mermaid_id']]
                    })
            
            # Step 5: Insert relationships
            for rel in kp_result.get('relationships', []):
                from_id = kp_id_mapping.get(rel['from'])
                to_id = kp_id_mapping.get(rel['to'])
                
                if from_id and to_id:
                    conn.execute(text("""
                        INSERT INTO document_kp_relationships (
                            unique_content_id, from_kp_id, to_kp_id, relationship_type,
                            teacher_id, version
                        ) VALUES (
                            :unique_content_id, :from_id, :to_id, :rel_type,
                            :teacher_id, :version
                        )
                    """), {
                        "unique_content_id": unique_content_id,
                        "from_id": from_id,
                        "to_id": to_id,
                        "rel_type": rel['type'],
                        "teacher_id": teacher_id,
                        "version": new_version
                    })
            
            print(f"✅ Saved KP map: {len(kp_result['knowledge_points'])} points, "
                  f"{len(kp_result.get('relationships', []))} relationships, "
                  f"version {new_version}")
            
            return new_version


# --- API Endpoints ---

@router.post("/extract", response_model=KPExtractionResponse)
async def extract_kp_endpoint(request: KPExtractionRequest):
    """
    Extract knowledge points from a document.
    
    This is triggered by teachers in Generator Settings UI after:
    1. Document ingestion is complete
    2. Teacher previews document content
    3. Teacher clicks "提取知識點" button
    
    Workflow:
    1. Check if KPs already exist (unless force_regenerate=true)
    2. Retrieve document content
    3. Call LLM to extract KPs
    4. Save to database
    5. Return KP map for frontend visualization
    """
    job_id = None
    current_task_id = None
    try:
        # Create job for tracking
        job_id = await run_in_db_pool(
            db_logger.create_job,
            user_id=request.teacher_id,
            input_prompt=f"[KP_EXTRACT] content_id={request.unique_content_id}",
            workflow_type='kp_extraction'
        )
        
        # Check if KPs already exist
        if not request.force_regenerate:
            def _check_existing(content_id, teacher_id):
                with engine.connect() as conn:
                    return conn.execute(text("""
                        SELECT version, COUNT(*) as kp_count
                        FROM document_knowledge_points
                        WHERE unique_content_id = :content_id 
                        AND teacher_id = :teacher_id
                        AND is_active = true
                        GROUP BY version
                    """), {
                        "content_id": content_id,
                        "teacher_id": teacher_id
                    }).fetchone()
            
            existing = await run_in_db_pool(_check_existing, request.unique_content_id, request.teacher_id)
                
            if existing:
                return KPExtractionResponse(
                    status="exists",
                    message=f"KP map already exists (version {existing[0]}, {existing[1]} points). Use force_regenerate=true to extract again.",
                    kp_map=None
                )
        
        # Step 1: Retrieve document pages (Stable non-LLM node: Conditional logging)
        try:
            file_name, pages = await _get_document_pages(request.unique_content_id)
            db_logger.logger.info(f"KP Extraction: Retrieved {len(pages)} pages for content {request.unique_content_id}")
        except Exception as e:
            # Only create a task record if it fails
            failed_task_id = await run_in_db_pool(
                db_logger.create_task,
                job_id=job_id,
                agent_name="kp_extractor",
                task_input={"unique_content_id": request.unique_content_id}
            )
            await run_in_db_pool(
                db_logger.update_task,
                task_id=failed_task_id,
                status='failed',
                error_message=f"Failed to retrieve document content: {str(e)}"
            )
            raise
        
        # Step 2: Extract document summary
        document_summary = extract_document_summary(pages)
        
        # Step 3: Call LLM to extract KPs (LLM node: Milestone logging)
        current_task_id = await run_in_db_pool(
            db_logger.create_task,
            job_id=job_id,
            agent_name="kp_extractor",
            task_input={
                "file_name": file_name,
                "summary_length": len(document_summary),
                "page_count": len(pages)
            }
        )
        task_id = current_task_id
        
        start_time = time.perf_counter()
        # Call LLM based extraction
        extraction_data = await extract_knowledge_points(
            document_summary=document_summary,
            file_name=file_name
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Unpack results and usage
        kp_result = extraction_data["kp_map"]
        usage = extraction_data["usage"]
        
        # Validate and enhance relationship diversity
        kp_result = _enhance_relationship_diversity(kp_result)
        
        # Calculate cost
        estimated_cost = db_logger.calculate_llm_cost(
            usage["model_name"], 
            usage["prompt_tokens"], 
            usage["completion_tokens"]
        )
        
        await run_in_db_pool(
            db_logger.update_task,
            task_id=task_id,
            status='completed',
            duration_ms=duration_ms,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            estimated_cost_usd=estimated_cost,
            model_name=usage["model_name"],
            output={
                "message": f"Extracted {len(kp_result['knowledge_points'])} KPs and {len(kp_result.get('relationships', []))} relationships.",
                "kp_count": len(kp_result['knowledge_points']),
                "relationship_count": len(kp_result.get('relationships', [])),
                "relationship_types": _count_relationship_types(kp_result.get('relationships', []))
            }
        )
        current_task_id = None # Task successfully completed
        
        # Step 4: Save to database
        version = await run_in_db_pool(
            _save_kp_to_database,
            unique_content_id=request.unique_content_id,
            teacher_id=request.teacher_id,
            kp_result=kp_result,
            job_id=job_id
        )
        
        kp_result['version'] = version
        
        # Update job status
        await run_in_db_pool(db_logger.update_job_status, job_id, 'completed')
        
        return KPExtractionResponse(
            status="success",
            message=f"Successfully extracted {len(kp_result['knowledge_points'])} knowledge points (version {version})",
            kp_map=kp_result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Only print full traceback for unexpected errors.
        # ValueError from the extractor means a known, handled failure (short file, bad LLM output).
        if isinstance(e, ValueError):
            db_logger.logger.warning(f"KP Extraction expected failure for job {job_id}: {e}")
        else:
            import traceback
            traceback.print_exc()

        if job_id:
            await run_in_db_pool(db_logger.update_job_status, job_id, 'failed', error_message=str(e))

        if current_task_id:
            await run_in_db_pool(
                db_logger.update_task,
                task_id=current_task_id,
                status='failed',
                error_message=str(e)
            )

        # Determine a user-friendly message based on the exception type
        if isinstance(e, ValueError):
            user_msg = str(e)
        elif "JSONDecodeError" in type(e).__name__:
            user_msg = "AI 回傳格式異常，請稍後重試"
        else:
            user_msg = f"提取失敗：{str(e)}"

        return KPExtractionResponse(
            status="error",
            message=user_msg,
            error=str(e)
        )




def _sync_get_kp_map(unique_content_id: int, teacher_id: int, version: Optional[int] = None):
    with engine.connect() as conn:
        # Build query
        if version:
            kp_query = text("""
                SELECT id, mermaid_node_id, knowledge_point_name, kp_level,
                       kp_description, confidence_score, parent_kp_id, version
                FROM document_knowledge_points
                WHERE unique_content_id = :content_id 
                AND teacher_id = :teacher_id
                AND version = :version
                ORDER BY id
            """)
            params = {"content_id": unique_content_id, "teacher_id": teacher_id, "version": version}
        else:
            kp_query = text("""
                SELECT id, mermaid_node_id, knowledge_point_name, kp_level,
                       kp_description, confidence_score, parent_kp_id, version
                FROM document_knowledge_points
                WHERE unique_content_id = :content_id 
                AND teacher_id = :teacher_id
                AND is_active = true
                ORDER BY id
            """)
            params = {"content_id": unique_content_id, "teacher_id": teacher_id}
        
        kp_rows = conn.execute(kp_query, params).fetchall()
        
        if not kp_rows:
            return None, "no_content"
        
        used_version = kp_rows[0][7]
        
        # Build knowledge points list
        knowledge_points = []
        id_to_mermaid = {}
        
        for row in kp_rows:
            db_id, mermaid_id, name, level, description, confidence, parent_id, _ = row
            id_to_mermaid[db_id] = mermaid_id
            
            knowledge_points.append({
                "mermaid_id": mermaid_id,
                "name": name,
                "level": level,
                "description": description,
                "confidence": confidence,
                "parent_mermaid_id": None  # Will update below
            })
        
        # Update parent_mermaid_id
        for i, row in enumerate(kp_rows):
            parent_id = row[6]
            if parent_id and parent_id in id_to_mermaid:
                knowledge_points[i]["parent_mermaid_id"] = id_to_mermaid[parent_id]
        
        # Get relationships
        rel_query = text("""
            SELECT r.from_kp_id, r.to_kp_id, r.relationship_type
            FROM document_kp_relationships r
            JOIN document_knowledge_points kp_from ON r.from_kp_id = kp_from.id
            WHERE kp_from.unique_content_id = :content_id
            AND r.teacher_id = :teacher_id
            AND r.version = :version
        """)
        rel_rows = conn.execute(rel_query, {
            "content_id": unique_content_id,
            "teacher_id": teacher_id,
            "version": used_version
        }).fetchall()
        
        relationships = []
        for row in rel_rows:
            from_id, to_id, rel_type = row
            if from_id in id_to_mermaid and to_id in id_to_mermaid:
                relationships.append({
                    "from": id_to_mermaid[from_id],
                    "to": id_to_mermaid[to_id],
                    "type": rel_type
                })
        
        # Build mermaid graph with relationship labels
        mermaid_lines = ["graph TD"]
        for kp in knowledge_points:
            # Sanitize name to prevent breaking mermaid syntax
            safe_name = kp['name'].replace('"', "'").replace('[', '(').replace(']', ')')
            mermaid_lines.append(f"    {kp['mermaid_id']}[\"{safe_name}\"]")
        
        # Add relationships with type-specific styling
        for rel in relationships:
            rel_type = rel['type']
            from_id = rel['from']
            to_id = rel['to']
            
            if rel_type == 'prerequisite':
                # Solid line with label (前置知識)
                mermaid_lines.append(f"    {from_id} -->|先備知識| {to_id}")
            elif rel_type == 'composition':
                # Solid line with label (包含關係)
                mermaid_lines.append(f"    {from_id} -->|包含| {to_id}")
            elif rel_type == 'contrast':
                # Dotted line with label (對比概念)
                mermaid_lines.append(f"    {from_id} -.比較.- {to_id}")
            elif rel_type == 'extension':
                # Dotted arrow with label (延伸應用)
                mermaid_lines.append(f"    {from_id} -.進階.-> {to_id}")
            else:
                # Fallback to plain arrow
                mermaid_lines.append(f"    {from_id} --> {to_id}")
        
        kp_map = {
            "knowledge_points": knowledge_points,
            "relationships": relationships,
            "mermaid_graph": "\n".join(mermaid_lines),
            "version": used_version
        }
        
        return {
            "unique_content_id": unique_content_id,
            "teacher_id": teacher_id,
            "version": used_version,
            "kp_map": kp_map
        }, None

@router.get("/{unique_content_id}/{teacher_id}", response_model=KPRetrievalResponse)
async def get_kp_map(unique_content_id: int, teacher_id: int, version: Optional[int] = None):
    """
    Retrieve existing KP map for a document.
    
    Args:
        unique_content_id: Document ID
        teacher_id: Teacher ID
        version: Optional version number (default: latest active version)
    """
    try:
        result, error = await run_in_db_pool(_sync_get_kp_map, unique_content_id, teacher_id, version)
        
        if error == "no_content":
            from fastapi import Response
            return Response(status_code=204)
            
        return KPRetrievalResponse(**result)
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to retrieve KP map: {str(e)}")
            


def _count_relationship_types(relationships: List[Dict]) -> Dict[str, int]:
    """Count the distribution of relationship types."""
    from collections import Counter
    types = [rel.get('type', 'unknown') for rel in relationships]
    return dict(Counter(types))


def _enhance_relationship_diversity(kp_result: Dict) -> Dict:
    """
    Enhance relationship diversity if it's too uniform.
    If more than 80% of relationships are the same type, smart adjust some of them.
    """
    relationships = kp_result.get('relationships', [])
    
    if not relationships or len(relationships) < 3:
        return kp_result  # Too few relationships to adjust
    
    # Count relationship types
    type_counts = _count_relationship_types(relationships)
    total = len(relationships)
    
    # Check if any single type dominates (>80%)
    dominant_type = None
    dominant_count = 0
    for rel_type, count in type_counts.items():
        if count / total > 0.8:
            dominant_type = rel_type
            dominant_count = count
            break
    
    if not dominant_type:
        return kp_result  # Already diverse enough
    
    print(f"⚠️ Relationship diversity issue detected: {dominant_count}/{total} are '{dominant_type}'")
    
    # Smart adjustment strategy
    knowledge_points = {kp['mermaid_id']: kp for kp in kp_result.get('knowledge_points', [])}
    adjusted_relationships = []
    adjusted_count = 0
    target_adjustments = min(3, int(total * 0.3))  # Adjust up to 30% or 3 relationships
    
    for i, rel in enumerate(relationships):
        if rel['type'] == dominant_type and adjusted_count < target_adjustments:
            from_kp = knowledge_points.get(rel['from'])
            to_kp = knowledge_points.get(rel['to'])
            
            if from_kp and to_kp:
                # Intelligent type suggestion based on KP levels and names
                new_type = _suggest_alternative_relationship_type(
                    from_kp, to_kp, dominant_type
                )
                
                if new_type != dominant_type:
                    rel['type'] = new_type
                    adjusted_count += 1
                    print(f"  📝 Adjusted: {rel['from']} -> {rel['to']}: {dominant_type} → {new_type}")
        
        adjusted_relationships.append(rel)
    
    kp_result['relationships'] = adjusted_relationships
    print(f"✅ Adjusted {adjusted_count} relationships for diversity")
    
    return kp_result


def _suggest_alternative_relationship_type(from_kp: Dict, to_kp: Dict, avoid_type: str) -> str:
    """
    Suggest an alternative relationship type based on KP characteristics.
    """
    from_name = from_kp['name'].lower()
    to_name = to_kp['name'].lower()
    from_level = from_kp['level']
    to_level = to_kp['level']
    
    # Strategy 1: Check for prerequisite keywords
    prerequisite_keywords = ['基礎', '入門', '概念', '原理', '理論', '定義']
    advanced_keywords = ['進階', '應用', '實作', '實踐', '深度', '高級']
    
    if any(kw in from_name for kw in prerequisite_keywords) and avoid_type != 'prerequisite':
        if any(kw in to_name for kw in advanced_keywords):
            return 'prerequisite'
    
    # Strategy 2: Check for contrast keywords in names
    contrast_pairs = [
        (['同步', 'sync'], ['非同步', 'async']),
        (['監督', 'supervised'], ['非監督', 'unsupervised']),
        (['靜態', 'static'], ['動態', 'dynamic']),
        (['傳統', '舊', 'traditional'], ['新興', '新', 'modern']),
    ]
    
    if avoid_type != 'contrast':
        for pair1, pair2 in contrast_pairs:
            if any(w in from_name for w in pair1) and any(w in to_name for w in pair2):
                return 'contrast'
            if any(w in to_name for w in pair1) and any(w in from_name for w in pair2):
                return 'contrast'
    
    # Strategy 3: Check for extension based on levels
    if avoid_type != 'extension':
        if from_level == 'core_concept' and to_level == 'sub_technique':
            return 'extension'
        if '基礎' in from_name and ('應用' in to_name or '實作' in to_name):
            return 'extension'
    
    # Strategy 4: If from and to are at same level, consider contrast
    if avoid_type != 'contrast' and from_level == to_level:
        return 'contrast'
    
    # Fallback: prefer prerequisite over composition
    if avoid_type == 'composition':
        return 'prerequisite'
    
    return avoid_type  # No better alternative found


# ==================== KP Promote Endpoint ====================

class KPPromoteRequest(BaseModel):
    """Request to promote extracted KPs into the permanent knowledge_points table."""
    unique_content_id: int = Field(..., description="Source document unique_content_id")
    kp_names: List[str] = Field(..., description="Names of the KPs to promote")
    unit_id: int = Field(..., description="Target unit_id for the promoted KPs")
    course_id: int = Field(..., description="Target course_id")


def _sync_promote_kps(unique_content_id: int, kp_names: List[str], unit_id: int, course_id: int):
    """
    Promote selected document_knowledge_points into the knowledge_points table.
    Uses ON CONFLICT DO NOTHING so safe to call multiple times.
    Returns the list of promoted KP records (id, name, source_name).
    """
    with engine.connect() as conn:
        with conn.begin():
            # Get source file name for source_name label
            file_row = conn.execute(text("""
                SELECT file_name FROM uploaded_contents
                WHERE unique_content_id = :ucid
                LIMIT 1
            """), {"ucid": unique_content_id}).fetchone()

            source_name = file_row.file_name if file_row else f"文件 #{unique_content_id}"

            promoted = []
            for name in kp_names:
                name = name.strip()
                if not name:
                    continue

                # Check if this KP already exists in this course
                existing = conn.execute(text("""
                    SELECT id, name, source_name FROM knowledge_points
                    WHERE course_id = :course_id AND name = :name
                    LIMIT 1
                """), {"course_id": course_id, "name": name}).fetchone()

                if existing:
                    promoted.append({
                        "id": existing.id,
                        "name": existing.name,
                        "source_name": existing.source_name,
                        "source_type": "extracted",
                        "already_existed": True,
                    })
                else:
                    result = conn.execute(text("""
                        INSERT INTO knowledge_points
                            (unit_id, course_id, name, display_order, source_type, source_name, source_id)
                        VALUES
                            (:unit_id, :course_id, :name, 4, 'extracted', :source_name, :source_id)
                        RETURNING id, name
                    """), {
                        "unit_id": unit_id,
                        "course_id": course_id,
                        "name": name,
                        "source_name": source_name,
                        "source_id": unique_content_id,
                    }).fetchone()

                    promoted.append({
                        "id": result.id,
                        "name": result.name,
                        "source_name": source_name,
                        "source_type": "extracted",
                    })

            return promoted


@router.post("/promote", tags=["Knowledge Point Extraction"])
async def promote_kps(request: KPPromoteRequest):
    """
    Promote selected extracted KPs into the confirmed unit knowledge_points table.

    Called when a teacher clicks '+ Add to Unit' in the Extracted Suggestions panel.
    Returns the list of promoted KP records with their integer IDs for use in generation.
    """
    try:
        promoted = await run_in_db_pool(
            _sync_promote_kps,
            unique_content_id=request.unique_content_id,
            kp_names=request.kp_names,
            unit_id=request.unit_id,
            course_id=request.course_id,
        )
        return {
            "status": "success",
            "promoted_count": len([p for p in promoted if not p.get("already_existed")]),
            "already_existed_count": len([p for p in promoted if p.get("already_existed")]),
            "knowledge_points": promoted,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"KP promotion failed: {str(e)}")
