"""
Teacher Data Router: 處理教師端教材資料管理功能

此 router 包含：
1. 取得教材列表 (get_materials)
2. 更新教材名稱 (update_material_name)
3. 文件匯入處理 (ingest_document)
"""
import os
import shutil
import tempfile
import mimetypes
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Query
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 2: JWT 認證
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import Table, select, update, delete, desc, func, insert

from backend.app.agents.teacher_agent.ingestion import process_file
from backend.app.utils.db_logger import engine, metadata, generated_contents, orchestration_jobs
from backend.app.config.settings import settings
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.time_utils import get_now_taipei

# Create router
router = APIRouter(prefix="/api/v1", tags=["Teacher Data Management"])

# --- Reflect tables ---
try:
    uploaded_contents_table = Table('uploaded_contents', metadata, autoload_with=engine)
    unique_contents_table = Table('unique_contents', metadata, autoload_with=engine)
    document_content_table = Table('document_content', metadata, autoload_with=engine)
    course_contents_table = Table('course_contents', metadata, autoload_with=engine)
    attachments_table = Table('attachments', metadata, autoload_with=engine)
    course_units_table = Table('course_units', metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting tables: {e}")
    uploaded_contents_table = None
    document_content_table = None

# --- Pydantic Models ---

class Material(BaseModel):
    id: int
    name: str = Field(alias='file_name')
    unique_content_id: int
    processing_status: Optional[str] = 'completed'
    created_at: Optional[str] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None

class UpdateMaterialRequest(BaseModel):
    name: str

class IngestResponse(BaseModel):
    unique_content_id: int
    uploaded_content_id: Optional[int] = None
    file_name: str
    message: str

class GeneratedMaterial(BaseModel):
    id: int
    title: str
    content_type: str
    content_subtype: Optional[str] = None
    created_at: str
    job_id: int
    unit_id: Optional[int] = None

class IngestGeneratedRequest(BaseModel):
    generated_content_id: int
    course_id: int
    force_reprocess: bool = False

# --- Data Management Endpoints ---

@router.get("/materials", response_model=List[Material])
async def get_materials(course_id: int):
    """
    Endpoint to get all materials (uploaded contents) for a given course.
    Queries uploaded_contents table directly.
    """
    if uploaded_contents_table is None or unique_contents_table is None:
        raise HTTPException(status_code=500, detail="Database tables not found.")
    
    # Join uploaded_contents with unique_contents
    j = uploaded_contents_table.join(
        unique_contents_table,
        uploaded_contents_table.c.unique_content_id == unique_contents_table.c.id,
        isouter=True
    )
    
    query = select(
        uploaded_contents_table.c.id,
        uploaded_contents_table.c.file_name,
        uploaded_contents_table.c.unique_content_id,
        uploaded_contents_table.c.created_at,
        uploaded_contents_table.c.file_path,
        unique_contents_table.c.processing_status,
        unique_contents_table.c.original_file_type.label('file_type')
    ).select_from(j).where(
        uploaded_contents_table.c.course_id == course_id
    ).order_by(uploaded_contents_table.c.created_at.desc())

    try:
        def _sync_get_materials(cid):
            with engine.connect() as conn:
                 result = conn.execute(query)
                 rows = result.fetchall()
                 material_list = []
                 for row in rows:
                     material_list.append({
                         "id": row.id,
                         "file_name": row.file_name,
                         "unique_content_id": row.unique_content_id,
                         "processing_status": row.processing_status if row.processing_status else 'completed',
                         "created_at": (row.created_at.isoformat() if row.created_at.tzinfo else row.created_at.isoformat() + "Z") if row.created_at else None,
                         "file_path": row.file_path,
                         "file_type": getattr(row, 'file_type', None)
                     })
                 return material_list

        return await run_in_db_pool(_sync_get_materials, course_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")

@router.delete("/materials/{material_id}", status_code=204)
async def delete_material(material_id: int):
    """
    Endpoint to delete a material (uploaded content).
    Only deletes the link in uploaded_contents, not the unique_content (unless we implement ref counting).
    """
    if uploaded_contents_table is None:
        raise HTTPException(status_code=500, detail="Database tables not found.")
        
    try:
        def _sync_delete_material(mid):
            with engine.connect() as conn:
                # 1. Get file path before delete
                query = select(uploaded_contents_table.c.file_path).where(uploaded_contents_table.c.id == mid)
                row = conn.execute(query).fetchone()
                
                if not row:
                    return "not_found"
                
                file_path = row.file_path
                
                # 2. Delete the record
                stmt = delete(uploaded_contents_table).where(uploaded_contents_table.c.id == mid)
                result = conn.execute(stmt)
                if result.rowcount == 0:
                     return "not_found"
                conn.commit()
                
                # 3. Check if we should delete file (Ref Count)
                # Only delete if file_path is set (not NULL) and looks like a file we manage
                if file_path:
                    # Count remaining references
                    count_query = select(func.count()).select_from(uploaded_contents_table).where(uploaded_contents_table.c.file_path == file_path)
                    count = conn.execute(count_query).scalar()
                    
                    if count == 0:
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                print(f"Deleted physical file: {file_path}")
                        except OSError as e:
                            print(f"Error deleting file {file_path}: {e}")
            return None

        error = await run_in_db_pool(_sync_delete_material, material_id)
        if error == "not_found":
             raise HTTPException(status_code=404, detail="Material not found")
        return
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database delete failed: {e}")

@router.patch("/materials/{material_id}", status_code=204)
async def update_material_name(material_id: int, request: UpdateMaterialRequest):
    """
    Endpoint to update the name of a material.
    """
    if uploaded_contents_table is None:
        raise HTTPException(status_code=500, detail="Database table 'uploaded_contents' not found.")
    stmt = update(uploaded_contents_table).where(uploaded_contents_table.c.id == material_id).values(file_name=request.name)
    try:
        def _sync_update_material_name(mid, stmt_obj):
            with engine.connect() as conn:
                result = conn.execute(stmt_obj)
                if result.rowcount == 0:
                    return "not_found"
                conn.commit()
            return None
            
        error = await run_in_db_pool(_sync_update_material_name, material_id, stmt)
        if error == "not_found":
            raise HTTPException(status_code=404, detail=f"Material with id {material_id} not found.")
        return
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    course_id: int = Form(1), 
    force_reprocess: bool = Form(None),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    unit_id: Optional[int] = Form(None),
    uploader_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 uploader_id
):
    """
    Endpoint to ingest a document from file upload or URL.
    
    Args:
        course_id: ID of the course
        uploader_id: ID of the uploader
        force_reprocess: If True, reprocess even if file already exists
                        If None, uses FORCE_INGEST from environment (.env)
        url: Optional URL for web content (if provided, file is ignored)
        file: Optional file to ingest (required if url is not provided)
    """
    # 如果沒有明確指定，從 settings 讀取
    if force_reprocess is None:
        force_reprocess = settings.rag.force_ingest
    # 驗證：必須提供 file 或 url 其中之一
    if not file and not url:
        raise HTTPException(
            status_code=400, 
            detail="Either 'file' or 'url' must be provided"
        )
    
    # 驗證：檔案不能為空
    if file:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="檔案為空")
    
    unique_content_id = None
    was_skipped = False
    file_name = ""
    message = ""

    if url:
        # 處理 URL（web loader）
        unique_content_id, was_skipped = await run_in_threadpool(
            process_file,
            file_path=url,  # web loader 會識別這是 URL
            uploader_id=uploader_id,
            course_id=course_id,
            course_unit_id=unit_id,  # Pass unit_id
            force_reprocess=force_reprocess,
            perform_async=True
        )
        
        if unique_content_id is None:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to process URL '{url}'. Check server logs for details."
            )
        
        # 建立顯示用的檔案名稱
        file_name = url.split('/')[-1] or 'web_content.html'
        if '?' in file_name:
            file_name = file_name.split('?')[0]
        if not file_name.endswith('.html'):
            file_name += '.html'
        
        # 根據 was_skipped 返回不同消息
        if was_skipped:
            message = f"此網址內容已存在(ID: {unique_content_id})，不重複匯入"
        else:
            message = f"成功匯入網址 '{url}'"
        
    else:
        # 處理檔案上傳（原有邏輯）
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            unique_content_id, was_skipped = await run_in_threadpool(
                process_file,
                file_path=file_path,
                uploader_id=uploader_id,
                course_id=course_id,
                course_unit_id=unit_id,  # Pass unit_id
                force_reprocess=force_reprocess,
                perform_async=True
            )
            file_name = file.filename
        
        if unique_content_id is None:
            raise HTTPException(status_code=500, detail="Failed to process the document.")
        
        # 根據 was_skipped 返回不同消息
        if was_skipped:
            message = f"此檔案已存在(ID: {unique_content_id})，不重複匯入"
        else:
            message = f"成功匯入檔案 '{file.filename}'"
        
    # 查詢 uploaded_content_id
    uploaded_content_id = None
    if uploaded_contents_table is not None:
        try:
            def _sync_get_uploaded_content_id(uid, cid):
                with engine.connect() as conn:
                    return conn.execute(
                        select(uploaded_contents_table.c.id).where(
                            (uploaded_contents_table.c.unique_content_id == uid) & 
                            (uploaded_contents_table.c.course_id == cid)
                        ).order_by(uploaded_contents_table.c.id.desc()).limit(1)
                    ).scalar_one_or_none()
            
            uploaded_content_id = await run_in_db_pool(_sync_get_uploaded_content_id, unique_content_id, course_id)
        except Exception as e:
            print(f"Error fetching uploaded_content_id: {e}")

    return IngestResponse(
        unique_content_id=unique_content_id,
        uploaded_content_id=uploaded_content_id,
        file_name=file_name,
        message=message
    )

@router.get("/generated_materials", response_model=List[GeneratedMaterial])
async def get_generated_materials(
    course_id: Optional[int] = Query(None),
    limit: int = 50,
    user_id: int = Depends(get_current_user_id)  # ✅ Phase 2: 從 JWT token 取得 user_id
):
    """
    Get list of materials generated by the AI agent.
    Joined with orchestration_jobs to filter by user.
    """
    try:
        # Join generated_contents and orchestration_jobs to get job info and filter by user
        # orchestration_jobs.final_output_id -> generated_contents.id
        # We want successfully completed jobs that produced content.
        
        # Filter by course if course_id is provided
        from sqlalchemy import and_
        where_clauses = []
        # 1. Join generated_contents with orchestration_jobs for basic metadata
        selectable = generated_contents.join(
            orchestration_jobs, 
            generated_contents.c.id == orchestration_jobs.c.final_output_id
        )
        
        if course_id:
            # ONLY include items explicitly added/generated in this course's contents
            selectable = selectable.join(
                course_contents_table,
                and_(
                    course_contents_table.c.source_id == generated_contents.c.id,
                    course_contents_table.c.source_type == 'generated_content'
                )
            )
            where_clauses.append(course_contents_table.c.course_id == course_id)
        else:
            where_clauses.append(orchestration_jobs.c.user_id == user_id)
            
        # Dynamically select columns based on whether course_id is provided
        unit_id_col = course_contents_table.c.unit_id.label("unit_id") if course_id else orchestration_jobs.c.input_config['job_context']['unit_id'].label("unit_id")
        content_subtype_col = course_contents_table.c.content_subtype.label("content_subtype") if course_id else orchestration_jobs.c.input_config['job_context']['material_type'].label("content_subtype")

        stmt = select(
            generated_contents.c.id,
            generated_contents.c.title,
            generated_contents.c.content_type,
            generated_contents.c.created_at,
            orchestration_jobs.c.id.label("job_id"),
            unit_id_col,
            content_subtype_col
        ).select_from(selectable).where(*where_clauses).order_by(
            generated_contents.c.created_at.desc()
        ).limit(limit)
        
        def _sync_get_generated_materials(uid, lim, stmt_obj):
            with engine.connect() as conn:
                rows = conn.execute(stmt_obj).fetchall()
                
                return [
                    GeneratedMaterial(
                        id=row.id,
                        title=row.title or "Untitled",
                        content_type=row.content_type,
                        content_subtype=row.content_subtype,
                        created_at=(row.created_at.isoformat() if row.created_at.tzinfo else row.created_at.isoformat() + "Z") if row.created_at else "",
                        job_id=row.job_id,
                        unit_id=row.unit_id
                    )
                    for row in rows
                ]

        return await run_in_db_pool(_sync_get_generated_materials, user_id, limit, stmt)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch generated materials: {e}")

@router.get("/generated_materials/{material_id}")
async def get_generated_material_content(material_id: int):
    """
    Get the full content of a specific generated material.
    """
    try:
        stmt = select(generated_contents).where(generated_contents.c.id == material_id)
        
        def _sync_get_content(stmt_obj):
            with engine.connect() as conn:
                row = conn.execute(stmt_obj).fetchone()
                if not row:
                    return None
                return {
                    "id": row.id,
                    "title": row.title,
                    "content": row.content,
                    "content_type": row.content_type
                }

        result = await run_in_db_pool(_sync_get_content, stmt)
            
        if not result:
            raise HTTPException(status_code=404, detail="Generated material not found")
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch generated material content: {e}")



@router.post("/materials/{unique_content_id}/attach_to_unit/{unit_id}")
async def attach_material_to_unit(
    unique_content_id: int, 
    unit_id: int, 
    file_name: Optional[str] = Form(None),
    uploader_id: int = Depends(get_current_user_id)
):
    """
    Attach an existing material (unique_content) to a unit as an attachment.
    This creates an 'attachment' record linking to the unique_content, 
    without duplicating the physical file.
    """
    if uploaded_contents_table is None or attachments_table is None:
        raise HTTPException(status_code=500, detail="Database tables not available.")
        
    try:
        # 1. Get file info from uploaded_contents or unique_contents
        # We prefer uploaded_contents to get the original filename context if possible, 
        # but unique_contents is the source of truth for the file.
        
        # Find the most recent uploaded_content for this unique_content_id to get a default filename
        stmt = select(uploaded_contents_table).where(
            uploaded_contents_table.c.unique_content_id == unique_content_id
        ).order_by(uploaded_contents_table.c.id.desc()).limit(1)
        
        def _sync_attach(uid, ucid, fname, upload_id):
            with engine.connect() as conn:
                # 1. Get metadata from combined unique_contents and uploaded_contents
                # We need file_size_bytes from unique_contents and file_path/name from uploaded_contents
                stmt_meta = select(
                    uploaded_contents_table.c.file_name,
                    uploaded_contents_table.c.file_path,
                    unique_contents_table.c.file_size_bytes
                ).join(
                    unique_contents_table,
                    uploaded_contents_table.c.unique_content_id == unique_contents_table.c.id
                ).where(
                    unique_contents_table.c.id == ucid
                ).order_by(uploaded_contents_table.c.id.desc()).limit(1)

                row = conn.execute(stmt_meta).fetchone()
                if not row:
                    return "not_found", "Material metadata not found."

                target_file_name = fname if fname else row.file_name
                target_file_path = row.file_path
                target_file_size = row.file_size_bytes or 1 # Avoid 0 to satisfy check constraint
                
                # 2. Insert into attachments
                conn.execute(insert(attachments_table).values(
                    file_name=target_file_name,
                    original_file_name=row.file_name,
                    file_path=target_file_path,
                    file_size_bytes=target_file_size,
                    file_type='url' if (target_file_path and (target_file_path.startswith('http://') or target_file_path.startswith('https://'))) else (target_file_name.split('.')[-1] if '.' in target_file_name else 'unknown'),
                    attachable_type='unit', # Must be lowercase 'unit' to satisfy check constraint
                    attachable_id=uid,
                    unique_content_id=ucid,
                    uploaded_by=upload_id,
                    uploaded_at=get_now_taipei()
                ))
                conn.commit()
                return "success", None

        status, msg = await run_in_db_pool(_sync_attach, unit_id, unique_content_id, file_name, uploader_id)
        
        if status == "not_found":
            raise HTTPException(status_code=404, detail=msg)
            
        return {"status": "success", "message": "Material attached to unit."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to attach material: {e}")

@router.get("/materials/{unique_content_id}/preview")
async def get_material_preview(unique_content_id: int):
    """
    Get the preview content (text) for a specific material.
    """
    if uploaded_contents_table is None or document_content_table is None:
        raise HTTPException(status_code=500, detail="Database tables not available.")
        
    try:
        # 1. Get file name, type and path (for URL)
        stmt_meta = (
            select(
                uploaded_contents_table.c.file_name,
                uploaded_contents_table.c.file_path,
                unique_contents_table.c.original_file_type
            )
            .join(
                unique_contents_table, 
                uploaded_contents_table.c.unique_content_id == unique_contents_table.c.id
            )
            .where(uploaded_contents_table.c.unique_content_id == unique_content_id)
        )
        
        # 2. Get pages content
        stmt_content = select(
            document_content_table.c.page_number,
            document_content_table.c.combined_human_text,
            document_content_table.c.structured_content  # ✅ Include structured content
        ).where(
            document_content_table.c.unique_content_id == unique_content_id
        ).order_by(document_content_table.c.page_number)
        
        def _sync_get_preview(s_meta, s_content):
            with engine.connect() as conn:
                meta_row = conn.execute(s_meta).fetchone()
                file_name = meta_row.file_name if meta_row else "Unknown File"
                file_path = meta_row.file_path if meta_row else None
                original_type = meta_row.original_file_type if meta_row else "unknown"
                
                rows = conn.execute(s_content).fetchall()
                
                pages = []
                for row in rows:
                    # Check for images in structured content
                    has_images = False
                    structured = row.structured_content or []
                    if structured and isinstance(structured, list):
                        has_images = any(item.get('type') == 'image' for item in structured)

                    pages.append({
                        "page_number": row.page_number,
                        "human_text": row.combined_human_text,
                        "structured_content": structured,
                        "has_images": has_images
                    })
                return file_name, file_path, original_type, pages

        file_name, file_path, original_type, pages = await run_in_db_pool(_sync_get_preview, stmt_meta, stmt_content)
        
        # Determine download/browse URL
        download_url = f"/api/v1/materials/{unique_content_id}/download"
        if file_path and (file_path.startswith('http://') or file_path.startswith('https://')):
            download_url = file_path

        return {
            "file_name": file_name,
            "file_type": original_type,
            "pages": pages,
            "download_url": download_url
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch preview: {e}")

from fastapi.responses import FileResponse

@router.get("/materials/{unique_content_id}/download")
async def download_material(unique_content_id: int, inline: bool = False):
    """
    Download the original file for a given material.
    param inline: If True, set Content-Disposition to inline for preview.
    """
    if uploaded_contents_table is None:
        raise HTTPException(status_code=500, detail="Database tables not available.")
    
    try:
        stmt = select(uploaded_contents_table.c.file_path, uploaded_contents_table.c.file_name).where(uploaded_contents_table.c.unique_content_id == unique_content_id)
        
        def _sync_get_file_info(stmt_obj):
            with engine.connect() as conn:
                row = conn.execute(stmt_obj).fetchone()
                if not row:
                    return None
                return row.file_path, row.file_name

        result = await run_in_db_pool(_sync_get_file_info, stmt)
            
        if not result:
            raise HTTPException(status_code=404, detail="Material not found")
            
        file_path, file_name = result
        
        if not os.path.exists(file_path):
             raise HTTPException(status_code=404, detail="File not found on server")
        
        # Determine media type and disposition
        media_type, _ = mimetypes.guess_type(file_path)
        if not media_type:
            media_type = 'application/octet-stream'
            
        disposition_type = 'inline' if inline else 'attachment'
             
        return FileResponse(
            path=file_path, 
            filename=file_name,
            media_type=media_type,
            content_disposition_type=disposition_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")

# Legacy endpoint /ingest_generated removed
# Ingestion is now handled automatically via ingest_course_content triggers in teacher_course_router.py
