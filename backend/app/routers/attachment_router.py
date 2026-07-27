"""
Attachment Router: 通用附件管理 API
支援多種實體類型的附件上傳、下載、列表、刪除功能
"""
import os
import shutil
import re
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy import insert, Table, Column, Integer, String, DateTime, BigInteger, Boolean, ForeignKey
from backend.app.utils.db_logger import engine, metadata
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Add authentication dependency
from backend.app.utils.concurrency import run_in_db_pool
from starlette.concurrency import run_in_threadpool
from backend.app.config.settings import settings
from backend.app.agents.teacher_agent.ingestion import process_file
from backend.app.utils.time_utils import get_now_taipei

router = APIRouter(prefix="/api", tags=["Attachments"])

# ==================== 配置 ====================
STORAGE_BASE = settings.attachment_dir
ALLOWED_TYPES = ["announcement", "assignment", "material", "exam", "unit"]
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.ppt', '.pptx',
    '.xls', '.xlsx', '.zip', '.rar', '.7z',
    '.jpg', '.jpeg', '.png', '.gif', '.txt'
}

# Reflect attachments table
try:
    attachments_table = Table('attachments', metadata, autoload_with=engine)
except Exception as e:
    print(f"Error reflecting attachments table: {e}")
    attachments_table = None


# ==================== Pydantic Models ====================

class AttachmentResponse(BaseModel):
    id: int
    file_name: str
    original_file_name: str
    file_size_bytes: int
    file_type: str
    uploaded_at: str
    uploaded_by_name: str
    download_url: str

# ==================== 工具函數 ====================

def sanitize_filename(filename: str) -> str:
    """清理檔名：移除危險字元，保留中文"""
    # 移除路徑分隔符和危險字元
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # 移除前後空白
    filename = filename.strip()
    # 如果檔名為空，使用預設名稱
    if not filename:
        filename = "unnamed_file"
    return filename

def validate_file_extension(filename: str) -> bool:
    """驗證檔案副檔名"""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS

def get_resource_table(resource_type: str) -> str:
    """取得資源對應的資料表名稱"""
    mapping = {
        'announcement': 'course_announcements',
        'assignment': 'course_contents',
        'material': 'course_contents',
        'exam': 'course_contents',
        'unit': 'course_units'
    }
    return mapping.get(resource_type)

async def verify_resource_exists(resource_type: str, resource_id: int) -> bool:
    """驗證資源是否存在 (Async)"""
    table_name = get_resource_table(resource_type)
    if not table_name:
        return False
    
    def _sync_verify(tname, rid, rtype):
        with engine.connect() as conn:
            if tname == 'course_contents':
                # 對於 unified table，額外檢查 content_type
                query = text(f"SELECT id FROM {tname} WHERE id = :id AND content_type = :type")
                result = conn.execute(query, {"id": rid, "type": rtype}).fetchone()
            else:
                query = text(f"SELECT id FROM {tname} WHERE id = :id")
                result = conn.execute(query, {"id": rid}).fetchone()
                
            return result is not None

    return await run_in_db_pool(_sync_verify, table_name, resource_id, resource_type)

# ==================== API Endpoints ====================

@router.post("/{resource_type}/{resource_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(
    resource_type: str,
    resource_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)  # ✅ Get actual user ID from JWT
):
    """
    上傳附件
    
    - **resource_type**: announcement, unit, assignment, material
    - **resource_id**: 對應資源的 ID
    - **file**: 檔案（最大 50MB）
    """
    # 1. 驗證資源類型
    if resource_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支援的資源類型：{resource_type}")
    
    # 2. 驗證資源存在
    if not await verify_resource_exists(resource_type, resource_id):
        raise HTTPException(status_code=404, detail=f"資源不存在：{resource_type} ID {resource_id}")
    
    # 3. 驗證檔案副檔名
    if not validate_file_extension(file.filename):
        raise HTTPException(status_code=400, detail=f"不支援的檔案類型，允許的副檔名：{', '.join(ALLOWED_EXTENSIONS)}")
    
    # 4. 檢查檔案大小
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"檔案過大，最大允許 50MB")
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="檔案為空")
    

    # 5. 產生安全的檔名
    original_filename = file.filename
    sanitized_filename = sanitize_filename(original_filename)
    safe_filename = sanitized_filename
    
    # 6. 處理文件上傳 (Ingestion + Storage)
    # 公告附件不應該進入 RAG 池，也不應出現在教材列表，因此跳過 process_file
    
    import tempfile
    import os
    import shutil
    import hashlib
    
    unique_content_id = None
    final_file_path = None
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, safe_filename)
        try:
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"檔案暫存失敗：{str(e)}")
        
        try:
            # 獲取所屬的 course_id
            async def _get_course_id(rtype, rid):
                tname = get_resource_table(rtype)
                # 對於 unit, announcement, exam, assignment，都可以追溯到 course_id
                # 這裡統一透過各自表內部的 course_id 欄位獲取
                def _sync_get_cid(tn, r_id):
                    with engine.connect() as conn:
                        query = text(f"SELECT course_id FROM {tn} WHERE id = :id")
                        result = conn.execute(query, {"id": r_id}).fetchone()
                        return result[0] if result else 1
                return await run_in_db_pool(_sync_get_cid, tname, rid)

            target_course_id = await _get_course_id(resource_type, resource_id)

            if resource_type == 'announcement':
                # ✅ 公告附件跳過 Ingestion (RAG) 流程，僅進行物理儲存
                # 計算 hash 用於檔名，避免衝突
                with open(temp_file_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                
                # 確保儲存目錄存在
                os.makedirs(settings.upload_dir, exist_ok=True)
                
                storage_filename = f"{file_hash}_{safe_filename}"
                dest_path = os.path.join(settings.upload_dir, storage_filename)
                
                if not os.path.exists(dest_path):
                    shutil.copy2(temp_file_path, dest_path)
                
                final_file_path = dest_path
                unique_content_id = None # 公告附件不進入 unique_contents
                print(f"Skipping ingestion for announcement attachment: {safe_filename}")
            else:
                # 其他類型繼續走正常 Ingestion 流程
                # 使用 threadpool 執行 process_file，確保不會阻塞主執行續
                print(f"Starting ingestion for file: {safe_filename}")
                unique_content_id, was_skipped = await run_in_threadpool(
                    process_file,
                    file_path=temp_file_path,
                    uploader_id=current_user_id,
                    course_id=target_course_id, # ✅ 使用動態獲取的 course_id
                    course_unit_id=resource_id if resource_type == 'unit' else None,
                    force_reprocess=False,
                    perform_async=True 
                )
                
                if unique_content_id:
                    def _get_path(ucid):
                        with engine.connect() as conn:
                            # 優先嘗試從 uploaded_contents 獲取 (這裡有最準確的路徑)
                            row = conn.execute(text("SELECT file_path FROM uploaded_contents WHERE unique_content_id = :uid ORDER BY id DESC LIMIT 1"), {"uid": ucid}).fetchone()
                            if row and row[0]: return row[0]
                            return None
                    
                    final_file_path = await run_in_threadpool(_get_path, unique_content_id)

        except Exception as e:
                import traceback
                print(f"Ingestion failed: {e}")
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"文件處理失敗: {str(e)}")

    if not final_file_path:
            raise HTTPException(status_code=500, detail="無法獲取文件儲存路徑")

    # 8. 插入資料庫記錄 (Attachments)
    try:
        now_local = get_now_taipei()
        
        def _sync_save_attachment(rtype, rid, fname, orig, fsize, fmime, fpath, uid, ucid, uploaded_at):
            with engine.connect() as conn:
                insert_query = text("""
                    INSERT INTO attachments (
                        attachable_type, attachable_id, file_name, 
                        original_file_name, file_size_bytes, file_type, 
                        file_path, uploaded_by, unique_content_id, uploaded_at
                    ) VALUES (
                        :type, :id, :filename, :original, :size, :mime, :path, :user, :ucid, :uploaded_at
                    ) ON CONFLICT ON CONSTRAINT idx_attachments_unique DO UPDATE SET
                        original_file_name = EXCLUDED.original_file_name,
                        file_size_bytes = EXCLUDED.file_size_bytes,
                        file_type = EXCLUDED.file_type,
                        file_path = EXCLUDED.file_path,
                        uploaded_by = EXCLUDED.uploaded_by,
                        unique_content_id = EXCLUDED.unique_content_id,
                        uploaded_at = EXCLUDED.uploaded_at
                    RETURNING id
                """)
                result = conn.execute(insert_query, {
                    "type": rtype,
                    "id": rid,
                    "filename": fname,
                    "original": orig,
                    "size": fsize,
                    "mime": fmime,
                    "path": fpath,
                    "user": uid,
                    "ucid": ucid,
                    "uploaded_at": uploaded_at
                })
                conn.commit()
                attachment_id = result.scalar()
                
                # 查詢完整資訊
                select_query = text("""
                    SELECT a.id, a.file_name, a.original_file_name, a.file_size_bytes, 
                           a.file_type, a.uploaded_at, u.full_name
                    FROM attachments a
                    LEFT JOIN users u ON a.uploaded_by = u.id
                    WHERE a.id = :id
                """)
                row = conn.execute(select_query, {"id": attachment_id}).fetchone()
                
                # Serialization helper: return as-is (naive Taipei time)
                def format_dt(dt):
                    if not dt: return ""
                    return dt.isoformat()

                return {
                    "id": row[0],
                    "file_name": row[2],  # 顯示原始檔名
                    "original_file_name": row[2],
                    "file_size_bytes": row[3],
                    "file_type": row[4],
                    "uploaded_at": format_dt(row[5]),
                    "uploaded_by_name": row[6] or "未知",
                    "download_url": f"/api/attachments/{row[0]}/download"
                }

        result_dict = await run_in_db_pool(
            _sync_save_attachment, 
            resource_type, resource_id, safe_filename, original_filename, file_size, 
            file.content_type or "application/octet-stream", str(final_file_path), current_user_id, unique_content_id, now_local
        )
        
        return AttachmentResponse(**result_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫操作失敗：{str(e)}")

@router.get("/{resource_type}/{resource_id}/attachments", response_model=List[AttachmentResponse])
async def list_attachments(resource_type: str, resource_id: int):
    """
    列出資源的所有附件
    """
    if resource_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支援的資源類型：{resource_type}")
    
    def _sync_list_attachments(rtype, rid):
        with engine.connect() as conn:
            query = text("""
                SELECT a.id, a.file_name, a.original_file_name, a.file_size_bytes, 
                       a.file_type, a.uploaded_at, u.full_name
            FROM attachments a
                LEFT JOIN users u ON a.uploaded_by = u.id
            WHERE a.attachable_type = :type AND a.attachable_id = :id
                ORDER BY a.uploaded_at DESC
            """)
            rows = conn.execute(query, {"type": rtype, "id": rid}).fetchall()
            
            result_list = []
            for row in rows:
                dt = row[5]
                uploaded_at_str = dt.isoformat() if dt else ""

                result_list.append({
                    "id": row[0],
                    "file_name": row[2],  # 顯示原始檔名
                    "original_file_name": row[2],
                    "file_size_bytes": row[3],
                    "file_type": row[4],
                    "uploaded_at": uploaded_at_str,
                    "uploaded_by_name": row[6] or "未知",
                    "download_url": f"/api/attachments/{row[0]}/download"
                })
            return result_list

    attachments_data = await run_in_db_pool(_sync_list_attachments, resource_type, resource_id)
    return [AttachmentResponse(**d) for d in attachments_data]

@router.get("/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: int):
    """
    下載附件（公開端點，學生可訪問）
    """
    def _sync_get_download_info(aid):
        with engine.connect() as conn:
            query = text("""
                SELECT file_path, original_file_name, file_type 
                FROM attachments 
                WHERE id = :id
            """)
            row = conn.execute(query, {"id": aid}).fetchone()
            if not row:
                return None
            return {
                "file_path": row[0],
                "filename": row[1],
                "media_type": row[2]
            }

    info = await run_in_db_pool(_sync_get_download_info, attachment_id)
    
    if not info:
        raise HTTPException(status_code=404, detail="附件不存在")
    
    file_path = Path(info["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案不存在於伺服器")
    
    return FileResponse(
        path=str(file_path),
        filename=info["filename"],  # 使用原始檔名
        media_type=info["media_type"] or 'application/octet-stream'
    )

@router.delete("/{resource_type}/{resource_id}/attachments/{attachment_id}")
async def delete_attachment(resource_type: str, resource_id: int, attachment_id: int):
    """
    刪除附件
    """
    if resource_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支援的資源類型：{resource_type}")
    
    def _sync_delete_attachment(aid, rtype, rid):
        with engine.connect() as conn:
            # 查詢附件資訊
            # 查詢附件資訊 (包含 Legacy Support: Unit 附件可能被標記為 'material')
            select_query = text("""
                SELECT file_path 
                FROM attachments 
                WHERE id = :id 
                AND (
                    (attachable_type = :type AND attachable_id = :resource_id)
                    OR 
                    (:type = 'unit' AND attachable_type = 'material' AND attachable_id = :resource_id)
                )
            """)
            row = conn.execute(select_query, {
                "id": aid,
                "type": rtype,
                "resource_id": rid
            }).fetchone()
            
            if not row:
                return None
            
            file_path_str = row[0]
            
            # 刪除關聯資料 (避免 ForeignKeyViolation)
            # 1. 刪除閱讀記錄
            conn.execute(text("DELETE FROM attachment_reading_logs WHERE attachment_id = :id"), {"id": aid})
            # 2. 將聊天紀錄中的 attachment_id 設為 NULL (保留聊天內容，但移除附件連結)
            conn.execute(text("UPDATE student_chatbot_dialogs SET attachment_id = NULL WHERE attachment_id = :id"), {"id": aid})

            # 刪除資料庫記錄
            delete_query = text("DELETE FROM attachments WHERE id = :id")
            conn.execute(delete_query, {"id": aid})
            conn.commit()
            return file_path_str

    file_path_str = await run_in_db_pool(_sync_delete_attachment, attachment_id, resource_type, resource_id)
    
    if not file_path_str:
        raise HTTPException(status_code=404, detail="附件不存在")
    
    # 3. 檢查是否還有其他引用指向同一實體檔案
    # 由於我們現在共用實體檔案，附件刪除時不應該刪除檔案
    # 除非我們實作了更複雜的 Reference Counting
    # 依照目前計畫：只刪除資料庫 attachments 記錄，保留實體檔案
    
    # file_path = Path(file_path_str)
    # print(f"[Delete Attachment] Processing deletion for ID {attachment_id}")
    # print(f"[Delete Attachment] Keeping physical file at: {file_path}")
    
    # 這裡我們完全跳過實體刪除 logic
    # if file_path.exists(): ...
    
    return {"message": "附件已刪除"}
