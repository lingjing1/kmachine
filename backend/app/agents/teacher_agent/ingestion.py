"""
Orchestrator for handling the ingestion of documents into the system.
"""
import hashlib
import time
import os
import shutil
from typing import Dict, Any, List, Tuple, Optional, Union

from datetime import datetime
from sqlalchemy import Table, select, insert, update, delete
from pgvector.sqlalchemy import Vector

from backend.app.config.settings import settings
from backend.app.db import engine, metadata
from backend.app.utils.time_utils import get_now_taipei
import backend.app.utils.db_logger as db_logger
from backend.app.utils.db_logger import log_task
import json
import base64
import logging

logger = logging.getLogger(__name__)

# --- Database Setup ---
# Using shared engine and metadata from backend.app.db

# Reflect tables used in this orchestrator
unique_contents = Table('unique_contents', metadata, autoload_with=engine)
uploaded_contents = Table('uploaded_contents', metadata, autoload_with=engine)
document_content = Table('document_content', metadata, autoload_with=engine)
document_chunks = Table('document_chunks', metadata, autoload_with=engine)
attachments = Table('attachments', metadata, autoload_with=engine)
document_knowledge_points = Table('document_knowledge_points', metadata, autoload_with=engine)
document_kp_relationships = Table('document_kp_relationships', metadata, autoload_with=engine)
reference_feedbacks = Table('reference_feedbacks', metadata, autoload_with=engine)

# --- Storage Setup ---
STORAGE_DIR = str(settings.upload_dir)
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR, exist_ok=True)

# --- Data Cleaning Functions (Phase 1+3) ---

import re
from typing import Tuple, List, Dict, Any

def _is_code_block(text: str) -> bool:
    """
    判斷文字是否為程式碼區塊
    
    改進版：提高檢測門檻，避免誤判一般技術文章為程式碼
    """
    if not text or len(text) < 20:  # ✅ 提高最小長度要求
        return False
    
    lines = text.split('\n')
    if len(lines) < 3:  # ✅ 要求至少3行
        return False
    
    code_indicators = 0
    total_lines = len(lines)
    
    # 強烈的程式碼指標
    strong_patterns = [
        r'^\s*(def|class|import|from .+ import)\s',  # Python 關鍵字
        r'^\s*(function|const|let|var|if|for|while)\s',  # JavaScript
        r'^\s*(public|private|void|int|String)\s',  # Java/C#
        r'[{}\[\]();].*[{}\[\]();]',  # 多個程式碼符號在同一行
        r'^\s*//.*$|^\s*/\*.*\*/$',  # 註解
    ]
    
    # 弱指標（需要更多數量才算）
    weak_patterns = [
        r'[=<>!]=|[+\-*/]=',  # 運算符
        r'\{.*\}',  # 單個 {}
    ]
    
    for line in lines:
        if not line.strip():
            continue
        
        # 檢查強指標
        for pattern in strong_patterns:
            if re.search(pattern, line):
                code_indicators += 2  # 強指標權重更高
                break
        else:
            # 檢查弱指標
            for pattern in weak_patterns:
                if re.search(pattern, line):
                    code_indicators += 0.5  # 弱指標權重低
                    break
    
    # ✅ 提高門檻：需要超過40%的行符合程式碼模式
    code_ratio = code_indicators / total_lines
    return code_ratio > 0.4


def _clean_text(text: str) -> str:
    """
    清理文字（標準化格式，移除噪音）
    
    處理:
    - 頁碼：移除單獨的頁碼行（text_splitter 會統一添加 [Page N]）
    - 頁碼佔位符：移除 ‹#› 等符號
    - 教師資訊：移除（非教學內容）
    - 多餘的空白和換行：標準化
    """
    if not text:
        return ""
    
    # 移除單獨的頁碼行（1-3位數字）
    text = re.sub(r'^\d{1,3}$', '', text, flags=re.MULTILINE)
    
    # 移除頁碼佔位符（‹#› 或 <#>）
    text = re.sub(r'[‹<]#+[›>]', '', text)
    
    # 移除教師資訊（特定格式）
    text = re.sub(r'資訊科學系.*?@mail\.ntue\.edu\.tw', '', text, flags=re.DOTALL)
    
    # 標準化換行（3個以上換行變成2個）
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 標準化空格（2個以上空格變成1個）
    text = re.sub(r' {2,}', ' ', text)
    
    return text.strip()


def _post_process_ocr(text: str) -> str:
    """
    OCR 後處理：移除噪音、修正常見錯誤
    
    策略：
    - 移除 OCR 噪音字元（來自圖標、線條等）
    - 修正數字間多餘空格
    - 過濾極短的片段
    - 移除純符號行
    """
    if not text:
        return ""
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        
        # ✅ 跳過空行
        if not line:
            continue
        
        # ✅ 跳過極短的行（<2 字符，可能是噪音）
        if len(line) < 2:
            continue
        
        # ✅ 跳過純符號行（如 "===", "---", "|||"）
        if all(c in '=-_|/\\*+~`^<>[]{}()' for c in line.replace(' ', '')):
            continue
        
        # ✅ 跳過過多符號的行（>50% 是符號）
        symbol_count = sum(1 for c in line if not c.isalnum() and c not in ' \n\t')
        if len(line) > 0 and symbol_count / len(line) > 0.5:
            continue
        
        # ✅ 移除明顯的 OCR 噪音字元（保留中文、英文、數字、常見標點）
        line = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()\\[\\]{}"\'+\\-=/*<>%$&@#]', '', line)
        
        # ✅ 修正數字間多餘空格（例如：「1 2 3」→「123」）
        line = re.sub(r'(\d)\s+(\d)', r'\1\2', line)
        
        # ✅ 移除多餘的空白
        line = ' '.join(line.split())
        
        if line:  # 最後檢查是否還有內容
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def _save_image_to_disk(base64_str: str, unique_content_id: int, page_number: int, image_index: int) -> Optional[str]:
    """
    Saves a base64 encoded image to the physical storage.
    Path: storage/uploads/images/{unique_content_id}/page_{page_number}_img_{image_index}.png
    """
    if not base64_str:
        return None
        
    try:
        # 1. 準備目錄
        relative_dir = os.path.join("images", str(unique_content_id))
        absolute_dir = os.path.join(STORAGE_DIR, relative_dir)
        os.makedirs(absolute_dir, exist_ok=True)
        
        # 2. 準備檔名
        file_name = f"page{page_number}_img{image_index}.png"
        relative_path = os.path.join(relative_dir, file_name)
        absolute_path = os.path.join(absolute_dir, file_name)
        
        # 3. 解碼並保存
        # Handle data URI prefix if present
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
            
        img_data = base64.b64decode(base64_str)
        with open(absolute_path, "wb") as f:
            f.write(img_data)
            
        return relative_path
    except Exception as e:
        print(f"Error saving image to disk: {e}")
        return None


def _clean_and_prepare_multimodal_content(
    structured_elements: List[Dict],
    unique_content_id: Optional[int] = None,
    page_number: int = 1,
    job_id: Optional[int] = None,
    parent_task_id: Optional[int] = None
) -> Tuple[str, Dict, List[Dict]]:
    """
    清理內容並準備多模態 metadata 與預覽用的結構化數據
    
    策略:
    - 程式碼：保留但用 [Code] 標記（因為很多教材是程式碼教學）
    - 頁碼：保留為 [Page N] 格式（用於 source 參考）
    - 圖片：存儲為物理文件，metadata 僅保留路徑 + 清理後的 OCR
    
    Args:
        structured_elements: List of {"type": "text"|"image", ...}
        unique_content_id: ID of the unique content (for folder naming)
        page_number: Current page number
    
    Returns:
        (text_for_chunking, multimodal_metadata, cleaned_elements)
    """
    from backend.app.services.document_loader.text_utils import smart_merge_lines, is_noise_line
    
    #收集 raw text lines
    raw_lines = []
    
    for elem in structured_elements:
        if elem.get("type") == "text":
            content = elem["content"]
            if content:
                # 按行分割，因為 smart_merge_lines 接受 list[str]
                raw_lines.extend(content.split('\n'))
    
    # 使用統一的處理邏輯（包含清理、程式碼檢測、合併）
    processed_text = smart_merge_lines(raw_lines)
    
    # 多模態部分：處理圖片
    images = []
    image_descriptions = []
    cleaned_elements = []
    
    for elem in structured_elements:
        if elem.get("type") == "image":
            # 保存完整圖片資訊
            vision_desc = elem.get("vision_description", "")
            vision_tokens = elem.get("vision_tokens", 0)
            vision_cost = elem.get("vision_cost", 0.0)
            cleaned_desc = _post_process_ocr(vision_desc)
            
            # ✅ 只在描述非空時才處理
            if cleaned_desc:
                # ✅ 保存圖片到磁碟，移除 base64
                img_path = None
                if unique_content_id:
                    img_path = _save_image_to_disk(
                        elem["base64"], 
                        unique_content_id, 
                        page_number, 
                        len(images)
                    )

                img_meta = {
                    "position": len(processed_text) + 1,
                    "image_path": img_path,
                    "url": f"/api/uploads/{img_path}" if img_path else None,
                    "vision_description": cleaned_desc,
                    "vision_tokens": vision_tokens,
                    "vision_cost": vision_cost
                }
                images.append(img_meta)
                
                # 在 text_for_chunking 中加入 Vision 描述
                vision_marker = f"<圖片描述>\n{cleaned_desc}\n</圖片描述>"
                image_descriptions.append(vision_marker)

                # 添加到清理後的元素列表
                cleaned_elem = elem.copy()
                cleaned_elem.pop("base64", None)
                cleaned_elem["image_path"] = img_path
                cleaned_elem["url"] = f"/api/uploads/{img_path}" if img_path else None
                cleaned_elem["vision_description"] = cleaned_desc
                cleaned_elements.append(cleaned_elem)
        else:
            # ✅ [Fix] 這裡也要過濾噪音文字，否則 Preview UI 還是會看到頁碼
            # 針對 PPTX 這種一個 shape 一個 element 的情況特別有效
            content = elem.get("content", "")
            if is_noise_line(content):
                continue
            cleaned_elements.append(elem)
    
    # 組合最終文字：處理過的文字 + 圖片描述
    final_text_parts = [processed_text] + image_descriptions
    text_for_chunking = "\n\n".join(final_text_parts)
    
    multimodal_metadata = {
        "images": images,
        "contains_code": "[code]" in processed_text,
    }
    
    return text_for_chunking, multimodal_metadata, cleaned_elements

# --- Main Orchestrator Logic ---
def process_file(file_path: str, uploader_id: int, course_id: int, course_unit_id: int = None, force_reprocess: bool = False, perform_async: bool = False) -> tuple[int | None, bool]:
    """
    Processes a single file for ingestion, using the new db_logger for all logging.
    
    Returns:
        tuple[int | None, bool]: (unique_content_id, was_skipped)
            - unique_content_id: ID of the content, or None if failed
            - was_skipped: True if file already existed and was skipped, False otherwise
    """
    file_name = os.path.basename(file_path)
    
    job_id = db_logger.create_job(
        user_id=uploader_id,
        input_prompt=f"[INGEST] Uploaded file: {file_name}",
        workflow_type='ingestion'
    )
    if not job_id:
        print(f"ERROR: Failed to create an ingestion job for file '{file_name}'. Aborting.")
        return None, False

    try:
        with engine.connect() as conn:
            with conn.begin() as transaction:
                last_task_id = None # Initialize for sequential parent_task_id logging

                # --- Task 1: Hashing and Get-Or-Create Unique Content ---
                task_id_hash = db_logger.create_task(job_id, "hash_file", task_input={"file_path": file_path}, parent_task_id=last_task_id)
                last_task_id = task_id_hash
                start_time = time.perf_counter()
                
                # ✅ 處理 URL 和本地文件的不同情況
                is_url = file_path.startswith('http://') or file_path.startswith('https://')
                
                if is_url:
                    # URL: 使用 URL 本身作為 hash 基礎
                    file_hash = hashlib.sha256(file_path.encode('utf-8')).hexdigest()
                    file_bytes = b''  # URL 沒有實際文件大小
                    file_size = 0
                else:
                    # 本地文件: 讀取並計算 hash
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                        file_hash = hashlib.sha256(file_bytes).hexdigest()
                        file_size = len(file_bytes)
                
                existing_id = conn.execute(select(unique_contents.c.id).where(unique_contents.c.content_hash == file_hash)).scalar_one_or_none()
                
                # 檢查現有記錄的狀態
                existing_status = None
                if existing_id:
                    existing_status = conn.execute(
                        select(unique_contents.c.processing_status).where(unique_contents.c.id == existing_id)
                    ).scalar_one_or_none()
                
                unique_content_id = None
                # 只有當內容存在且狀態為 'completed' 時才跳過
                # failed 或 in_progress 的內容應該重新處理
                if existing_id and existing_status == 'completed' and not force_reprocess:
                    unique_content_id = existing_id
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    db_logger.update_task(task_id_hash, 'completed', f"Content already exists with ID {unique_content_id} (status: {existing_status}).", duration_ms=duration_ms)
                    
                    # Store unique_content_id in job_context for easier tracking
                    db_logger.update_job_context(job_id, {"unique_content_id": unique_content_id})
                else:
                    if existing_id: # 重新處理（force_reprocess 或 status != 'completed'）
                        reason = "force_reprocess" if force_reprocess else f"status is '{existing_status}', needs reprocessing"
                        db_logger.create_task(job_id, "delete_old_content", task_input={"existing_id": existing_id}, parent_task_id=last_task_id)
                        
                        # ✅ Delete in order to satisfy Foreign Key constraints
                        # 1. Feedbacks on chunks must go first
                        conn.execute(delete(reference_feedbacks).where(reference_feedbacks.c.chunk_id.in_(
                            select(document_chunks.c.id).where(document_chunks.c.unique_content_id == existing_id)
                        )))
                        
                        # 2. Dependent content tables
                        conn.execute(delete(attachments).where(attachments.c.unique_content_id == existing_id))
                        conn.execute(delete(document_content).where(document_content.c.unique_content_id == existing_id))
                        conn.execute(delete(document_chunks).where(document_chunks.c.unique_content_id == existing_id))
                        conn.execute(delete(document_kp_relationships).where(document_kp_relationships.c.unique_content_id == existing_id))
                        conn.execute(delete(document_knowledge_points).where(document_knowledge_points.c.unique_content_id == existing_id))
                        conn.execute(delete(uploaded_contents).where(uploaded_contents.c.unique_content_id == existing_id))
                        
                        # Finally delete the master record
                        conn.execute(delete(unique_contents).where(unique_contents.c.id == existing_id))
                    
                    # ✅ 對於 URL，file_type 設為 'web'
                    if is_url:
                        file_type = 'web'
                    else:
                        file_type = file_name.split('.')[-1] if '.' in file_name else 'unknown'
                    
                    insert_stmt = insert(unique_contents).values(
                        content_hash=file_hash, 
                        file_size_bytes=file_size,
                        original_file_type=file_type,  # ✅ 使用 file_type 變數
                        processing_status='in_progress',
                        created_at=get_now_taipei()
                    ).returning(unique_contents.c.id)
                    unique_content_id = conn.execute(insert_stmt).scalar_one()
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    db_logger.update_task(task_id_hash, 'completed', f"Created new unique_content with ID {unique_content_id}.", duration_ms=duration_ms)

                    # Store unique_content_id in job_context for easier tracking
                    db_logger.update_job_context(job_id, {"unique_content_id": unique_content_id})

                # --- Task 2: Link Material to Course ---
                task_id_link = db_logger.create_task(job_id, "link_material", task_input={"unique_content_id": unique_content_id, "course_id": course_id, "uploader_id": uploader_id}, parent_task_id=last_task_id)
                last_task_id = task_id_link
                start_time = time.perf_counter()
                
                # --- Task 1.5: Persist File Storage ---
                stored_file_path = None
                if not is_url:
                    # 使用 hash + filename 避免衝突
                    storage_filename = f"{file_hash}_{file_name}"
                    dest_path = os.path.join(STORAGE_DIR, storage_filename)
                    
                    if not os.path.exists(dest_path):
                        shutil.copy2(file_path, dest_path)
                    
                    stored_file_path = dest_path

                if not conn.execute(select(uploaded_contents.c.id).where((uploaded_contents.c.unique_content_id == unique_content_id) & (uploaded_contents.c.course_id == course_id))).scalar_one_or_none():
                    # Check if file_path is a URL to save it
                    save_path = stored_file_path
                    if not save_path and file_path and (file_path.startswith('http://') or file_path.startswith('https://')):
                        save_path = file_path
                        
                    conn.execute(insert(uploaded_contents).values(
                        unique_content_id=unique_content_id, course_id=course_id,
                        unit_id=course_unit_id, # ✅ Save unit_id
                        uploader_id=uploader_id, file_name=file_name,
                        file_path=save_path,
                        created_at=get_now_taipei(),
                        updated_at=get_now_taipei()
                    ))
                else:
                    from sqlalchemy import func
                    # Check if file_path is a URL to save it
                    save_path = stored_file_path
                    if not save_path and file_path and (file_path.startswith('http://') or file_path.startswith('https://')):
                        save_path = file_path
                        
                    conn.execute(update(uploaded_contents).where(
                        (uploaded_contents.c.unique_content_id == unique_content_id) & 
                        (uploaded_contents.c.course_id == course_id)
                    ).values(
                        file_name=file_name,
                        updated_at=get_now_taipei(),
                        uploader_id=uploader_id,
                        file_path=save_path
                    ))
                
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                db_logger.update_task(task_id_link, 'completed', f"Linked content {unique_content_id} to course {course_id}.", duration_ms=duration_ms)

                # ✅ 更新跳過邏輯條件
                if existing_id and existing_status == 'completed' and not force_reprocess:
                    db_logger.update_job_status(job_id, 'completed')
                    return unique_content_id, True  # ✅ 返回 tuple，標記為已跳過

                # Use the stored path for processing if available (guarantees persistence for async)
                target_process_path = stored_file_path if stored_file_path else file_path
                
                # Close the transaction here for tasks 1 & 2
                
            # End of "with conn.begin()" - commits transactions for Task 1 & 2
        
        # Determine if we run the rest in background or foreground
        if perform_async:
            import threading
            t = threading.Thread(
                target=_process_file_content_background, 
                args=(target_process_path, unique_content_id, job_id, last_task_id, uploader_id, file_name, course_id)
            )
            t.start()
            logger.info(f"Ingestion: Processing '{file_name}' (Job {job_id})")
        else:
            _process_file_content_background(target_process_path, unique_content_id, job_id, last_task_id, uploader_id, file_name, course_id)

        return unique_content_id, False

    except Exception as e:
        print(f"ERROR: An error occurred during file ingestion for job {job_id}. Error: {e}")
        db_logger.update_job_status(job_id, 'failed', error_message=str(e))
        # The transaction will be rolled back automatically by the 'with' statement context manager if in "with" block
        # But here we might be outside.
        return None, False


def _process_file_content_background(file_path, unique_content_id, job_id, last_task_id, uploader_id, file_name, course_id):
    """
    Background worker to process file content (Load, Save, Chunk, Embed).
    """
    try:
        # Start a new DB session for the background thread
        with engine.connect() as conn:
            with conn.begin():
                # --- Task 3: Document Loading & Parsing ---
                from backend.app.services.document_loader import get_loader
                task_id_load = db_logger.create_task(job_id, "document_loader", task_input={"file_path": file_path}, parent_task_id=last_task_id)
                last_task_id = task_id_load
                start_time = time.perf_counter()
                
                try:
                    document = get_loader(file_path).load(file_path)
                    
                    # ✅ Check for title in metadata and update file_name if found (Mainly for WebLoader)
                    title = document.metadata.get('title')
                    if title:
                        logger.info(f"Title extraction: {title}")
                        conn.execute(
                            update(uploaded_contents)
                            .where((uploaded_contents.c.unique_content_id == unique_content_id) & (uploaded_contents.c.course_id == course_id))
                            .values(file_name=title)
                        )
                        # Make sure to update local variable for consistency if needed downstream
                        file_name = title 

                except Exception as e:
                    db_logger.update_task(task_id_load, 'failed', error_message=str(e))
                    raise e
                    
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                db_logger.update_task(task_id_load, 'completed', f"Loaded {len(document.pages)} pages. Title: {document.metadata.get('title', 'N/A')}", duration_ms=duration_ms)

                # --- Task 4: Save Document Content ---
                task_id_save_content = db_logger.create_task(job_id, "database_writer", task_input={"unique_content_id": unique_content_id}, parent_task_id=last_task_id)
                last_task_id = task_id_save_content
                start_time = time.perf_counter()
                preview_data = []
                
                for page in document.pages:
                    structured_json = getattr(page, 'structured_elements', [])
                    
                    # ✅ 傳入 unique_content_id, page_number 用於圖片存儲
                    text_for_chunking, mm_metadata, cleaned_elements = _clean_and_prepare_multimodal_content(
                        structured_json,
                        unique_content_id=unique_content_id,
                        page_number=page.page_number,
                        job_id=job_id,
                        parent_task_id=task_id_load
                    )
                    
                    # 暫存在 Page 物件（供 text_splitter 使用）
                    page.text_for_chunking = text_for_chunking
                    page.multimodal_metadata = mm_metadata
                    
                    if cleaned_elements:
                        preview_data.append({
                            "unique_content_id": unique_content_id,
                            "page_number": page.page_number,
                            "structured_content": cleaned_elements,  # ✅ 使用已清理的版本
                            "combined_human_text": text_for_chunking  # ✅ 純文字+OCR（不含 base64）
                        })
                
                if preview_data:
                    conn.execute(insert(document_content), preview_data)
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                db_logger.update_task(task_id_save_content, 'completed', f"Saved {len(preview_data)} pages of content.", duration_ms=duration_ms)
                
                # ✅ 聚合 Vision LLM 成本記錄 + 錯誤收集
                total_vision_tokens = 0
                total_vision_cost = 0.0
                total_images = 0
                vision_errors = []  # ✅ 收集錯誤
                
                for page_idx, page in enumerate(document.pages):
                    mm_metadata = getattr(page, 'multimodal_metadata', {})
                    for img_idx, img in enumerate(mm_metadata.get('images', [])):
                        total_vision_tokens += img.get('vision_tokens', 0)
                        total_vision_cost += img.get('vision_cost', 0.0)
                        total_images += 1
                        
                        # ✅ 檢查是否有錯誤（描述為空 = 失敗）
                        if not img.get('vision_description'):
                            vision_errors.append({
                                "page": page_idx + 1,
                                "image": img_idx + 1,
                                "reason": "Vision API failed or unsupported format"
                            })
                
                # 如果有圖片處理，創建單一 vision_llm 任務記錄
                if total_images > 0:
                    task_id_vision = db_logger.create_task(
                        job_id=job_id,
                        agent_name="vision_llm",
                        task_input={"image_count": total_images},
                        parent_task_id=last_task_id
                    )
                    last_task_id = task_id_vision
                    
                    # ✅ 準備輸出訊息（包含錯誤）
                    output_msg = f"Processed {total_images} images"
                    if vision_errors:
                        output_msg += f" ({len(vision_errors)} failed)"
                    
                    db_logger.update_task(
                        task_id=task_id_vision,
                        status='completed' if len(vision_errors) < total_images else 'failed',
                        output={
                            "images_processed": total_images,
                            "images_failed": len(vision_errors),
                            "errors": vision_errors  # ✅ 記錄錯誤詳情
                        },
                        duration_ms=0,
                        prompt_tokens=0,
                        completion_tokens=total_vision_tokens,
                        estimated_cost_usd=total_vision_cost,
                        model_name=settings.agent.vision_model
                    )


                # --- Task 5: Document Chunking ---
                from backend.app.services.text_splitter import chunk_document
                chunk_size = settings.rag.chunk_size
                chunk_overlap = settings.rag.chunk_overlap
                task_id_chunk = db_logger.create_task(job_id, "text_splitter", task_input={"chunk_size": chunk_size, "chunk_overlap": chunk_overlap}, parent_task_id=last_task_id)
                last_task_id = task_id_chunk
                start_time = time.perf_counter()
                chunks_with_metadata = chunk_document(pages=document.pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap, file_name=file_name, uploader_id=uploader_id)
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                db_logger.update_task(task_id_chunk, 'completed', f"Created {len(chunks_with_metadata)} chunks.", duration_ms=duration_ms)

                # --- Task 6: Generate Embeddings and Store Chunks ---
                task_id_embed = db_logger.create_task(job_id, "embedding_generator", task_input={"num_chunks_to_embed": len(chunks_with_metadata) if chunks_with_metadata else 0}, parent_task_id=last_task_id)
                last_task_id = task_id_embed
                start_time = time.perf_counter()
                if chunks_with_metadata:
                    from backend.app.services.embedding_service import embedding_service
                    
                    # Prepare static metadata once
                    uploaded_at_str = get_now_taipei().isoformat()
                    static_meta = {
                        "document_id": unique_content_id,
                        "document_name": file_name,
                        "course_id": course_id,
                        "uploaded_at": uploaded_at_str
                    }

                    # ✅ 處理三元組格式 (text, metadata, multimodal_metadata)
                    if chunks_with_metadata and len(chunks_with_metadata[0]) == 3:
                        texts_to_embed = [text for text, meta, mm_meta in chunks_with_metadata]
                        embeddings, usage = embedding_service.create_embeddings(texts_to_embed)
                        chunk_data = []
                        for i, ((text, meta, mm_meta), embedding) in enumerate(zip(chunks_with_metadata, embeddings)):
                            # Merge static meta into chunk metadata
                            enriched_meta = {**meta, **static_meta}
                            chunk_data.append({
                                "unique_content_id": unique_content_id,
                                "chunk_text": text,
                                "chunk_order": i,
                                "metadata": enriched_meta,
                                "multimodal_metadata": mm_meta,
                                "embedding": embedding
                            })
                    else:
                        texts_to_embed = [text for text, meta in chunks_with_metadata]
                        embeddings, usage = embedding_service.create_embeddings(texts_to_embed)
                        chunk_data = []
                        for i, ((text, meta), embedding) in enumerate(zip(chunks_with_metadata, embeddings)):
                            # Merge static meta into chunk metadata
                            enriched_meta = {**meta, **static_meta}
                            chunk_data.append({
                                "unique_content_id": unique_content_id,
                                "chunk_text": text,
                                "chunk_order": i,
                                "metadata": enriched_meta,
                                "multimodal_metadata": None,
                                "embedding": embedding
                            })
                    
                    conn.execute(insert(document_chunks), chunk_data)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    
                    # 計算 embedding 成本
                    total_tokens = usage.get("total_tokens", 0)
                    model = embedding_service._model_name
                    if "large" in model:
                        cost_per_1k = 0.00013
                    else:  # small or default
                        cost_per_1k = 0.00002
                    estimated_cost = (total_tokens / 1000.0) * cost_per_1k
                    
                    db_logger.update_task(
                        task_id_embed, 
                        'completed', 
                        f"Saved {len(chunk_data)} chunks.", 
                        duration_ms=duration_ms, 
                        prompt_tokens=total_tokens,  # ✅ 使用 total_tokens
                        model_name=model,  # ✅ 模型名稱
                        estimated_cost_usd=estimated_cost  # ✅ 計算成本
                    )
                else:
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    db_logger.update_task(task_id_embed, 'completed', "No chunks to embed.", duration_ms=duration_ms)

                # --- Task 7: Finalize Status ---
                task_id_finalize = db_logger.create_task(job_id, "finalize_status", task_input={"unique_content_id": unique_content_id}, parent_task_id=last_task_id)
                last_task_id = task_id_finalize
                start_time = time.perf_counter()
                conn.execute(update(unique_contents).where(unique_contents.c.id == unique_content_id).values(processing_status='completed'))
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                db_logger.update_task(task_id_finalize, 'completed', duration_ms=duration_ms)

        db_logger.update_job_status(job_id, 'completed')
        logger.info(f"Ingestion complete: '{file_name}'")

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        db_logger.update_job_status(job_id, 'failed', error_message=str(e))
        # Mark as failed in DB
        try:
            with engine.connect() as conn:
                with conn.begin():
                     conn.execute(update(unique_contents).where(unique_contents.c.id == unique_content_id).values(processing_status='failed'))
        except Exception as db_e:
            print(f"Failed to update status to failed: {db_e}")

    except Exception as e:
        print(f"ERROR: An error occurred during file ingestion for job {job_id}. Error: {e}")
        db_logger.update_job_status(job_id, 'failed', error_message=str(e))
        # The transaction will be rolled back automatically by the 'with' statement context manager
        return None, False  # ✅ 返回 tuple

if __name__ == '__main__':
    # This block remains for direct testing of the ingestion process
    # ✅ 從 settings 讀取 force_ingest（可透過環境變數 FORCE_INGEST 控制）
    from backend.app.config.settings import settings
    FORCE_REPROCESS = settings.rag.force_ingest
    print(f"--- Starting Multimodal Document Ingestion Test (Force Reprocess: {FORCE_REPROCESS}) ---")
    TEST_FILES_DIR = "test_files"
    if not os.path.isdir(TEST_FILES_DIR):
        print(f"Error: Test files directory not found at '{TEST_FILES_DIR}'.")
        exit()
    
    test_files = ["sample.pptx"] 
    
    for test_file in test_files:
        test_file_path = os.path.join(TEST_FILES_DIR, test_file)
        print("\n" + "="*50 + f"\nProcessing file: {test_file_path}\n" + "="*50)
        try:
            content_id, was_skipped = process_file(file_path=test_file_path, uploader_id=1, course_id=1, force_reprocess=FORCE_REPROCESS)
            if content_id:
                status = "skipped (already exists)" if was_skipped else "successfully ingested"
                print(f"\n--- File {status}. Unique Content ID: {content_id} ---")
            else:
                print(f"\n--- Failed to process file: {test_file_path} ---")
        except Exception as e:
            print(f"!!! FAILED to process {test_file_path}: {e} !!!")
    print("\n--- All Document Ingestion Tests Finished ---")


# Legacy function ingest_generated_content removed
# Use ingest_course_content instead

# --- New Ingestion Logic for Database-Stored Generated Content ---

@log_task(agent_name="course_content_saver", input_extractor=lambda *args, **kwargs: {"course_content_id": args[0] if args else kwargs.get("course_content_id")})
def ingest_course_content(
    course_content_id: int,
    force_reprocess: bool = False,
    job_id: Optional[int] = None,
    **kwargs
) -> Union[bool, Dict[str, Any]]:
    """
    Ingests content directly from the COURSE_CONTENTS table into GENERATED_CONTENT_CHUNKS.
    This is triggered when a user saves or updates a material/exam.
    
    Args:
        course_content_id: ID of the content in course_contents table
        force_reprocess: If True, skips hash check and forces re-ingestion.
    
    Returns:
        bool: Success status
    """
    # Define table reflection locally or ensure global reflection includes it
    generated_content_chunks = Table('generated_content_chunks', metadata, autoload_with=engine)
    course_contents = Table('course_contents', metadata, autoload_with=engine)
    
    try:
        with engine.begin() as conn:
            # 1. Fetch Content
            row = conn.execute(
                select(course_contents.c.content, course_contents.c.title, course_contents.c.content_type, course_contents.c.unit_id)
                .where(course_contents.c.id == course_content_id)
            ).first()
            
            if not row:
                print(f"Error: Course content ID {course_content_id} not found.")
                return False
                
            content_json = row.content
            title = row.title
            content_type = row.content_type
            unit_id = row.unit_id
            
            # 2. Filter & Prepare Text
            import copy
            if isinstance(content_json, dict):
                content_to_process = copy.deepcopy(content_json)
                
                # [NEW] Helper for recursive cleaning
                def _strip_large_data(data, extracted_imgs, depth=0):
                    """
                    Recursively removes large fields (retrieved_text_chunks, base64 images)
                    and extracts image metadata.
                    """
                    if isinstance(data, dict):
                        # 1. Remove large keys
                        if "retrieved_text_chunks" in data:
                            # Extract images from chunks before deletion
                            for chunk in data["retrieved_text_chunks"]:
                                mm = chunk.get("multimodal_metadata")
                                if mm and mm.get("images"):
                                    for img in mm["images"]:
                                        if img.get("base64"):
                                            # Migration/Legacy: Convert base64 to path if found
                                            # Use gen_{course_content_id} as folder for generated artifacts
                                            new_path = _save_image_to_disk(
                                                img["base64"], 
                                                f"gen_{course_content_id}", 
                                                0, # Page 0 for generated
                                                len(extracted_imgs)
                                            )
                                            img_copy = img.copy()
                                            img_copy.pop("base64", None)
                                            img_copy["image_path"] = new_path
                                            img_copy["url"] = f"/api/uploads/{new_path}"
                                            extracted_imgs.append(img_copy)
                                        else:
                                            extracted_imgs.append(img)
                            del data["retrieved_text_chunks"]
                        
                        # 2. Check for base64 images in potential multimodal struct
                        # (Recursively processing other fields)
                        for key, value in list(data.items()):
                            if key == "base64" and isinstance(value, str):
                                # If we find a lone base64, we might want to convert it, 
                                # but usually images are in the list.
                                pass
                            _strip_large_data(value, extracted_imgs, depth + 1)
                            
                    elif isinstance(data, list):
                        for item in data:
                            _strip_large_data(item, extracted_imgs, depth + 1)

                # [NEW] Extract multimodal metadata from references before deletion
                extracted_images = []
                _strip_large_data(content_to_process, extracted_images)
            else:
                content_to_process = content_json
                extracted_images = [] # No references to extract from
            
            # Prepare multimodal metadata for storage
            multimodal_metadata = {"images": extracted_images} if extracted_images else None

            # [NEW] Serialization Logic
            def _serialize_content_to_text(data: Any) -> str:
                """
                Converts structured content (JSON) into clean Markdown text for embedding.
                Prioritizes readability and token efficiency.
                """
                output_lines = []
                
                if isinstance(data, dict):
                    # Special handling for common content structures
                    # 1. Summary Report / Generated Material Structure
                    if "content" in data and isinstance(data["content"], list):
                        # Recursive call for the main content list
                        return _serialize_content_to_text(data["content"])

                    if "sections" in data and isinstance(data["sections"], list):
                        # Recursive call for the sections list (e.g. detailed summary)
                        return _serialize_content_to_text(data["sections"])
                    
                    # 2. Section / Highlight Object
                    title = data.get("section_title") or data.get("title")
                    if title:
                        output_lines.append(f"## {title}")
                    
                    # Keywords / KPs
                    kps = data.get("related_kps") or data.get("keywords")
                    if kps and isinstance(kps, list):
                        output_lines.append(f"**Keywords**: {', '.join(kps)}")
                    
                    # Content List / Body
                    content_list = data.get("content_list") or data.get("points")
                    if content_list and isinstance(content_list, list):
                        for item in content_list:
                            output_lines.append(f"- {item}")
                    
                    # Fallback for other keys if not matched above
                    # If we matched title/content_list, we skip generic processing to avoid duplication
                    if not (title or content_list):
                        # Generic dict processing
                        for k, v in data.items():
                            if k in ["type", "source_hash", "job_id", "display_type"]: continue # Skip metadata keys
                            if not v: continue
                            formatted_val = _serialize_content_to_text(v)
                            if formatted_val:
                                output_lines.append(f"**{k}**: {formatted_val}")
                                
                elif isinstance(data, list):
                    for item in data:
                        formatted_item = _serialize_content_to_text(item)
                        if formatted_item:
                            output_lines.append(formatted_item)
                            output_lines.append("") # Spacing between items
                            
                elif isinstance(data, str):
                    return data.strip()
                elif isinstance(data, (int, float, bool)):
                    return str(data)
                
                return "\n".join(output_lines).strip()

            if isinstance(content_to_process, str):
                text_content = content_to_process
            else:
                # [MODIFIED] Use smart serialization instead of json.dumps
                text_content = _serialize_content_to_text(content_to_process)
                # Fallback if empty (e.g. strange structure), though unlikely
                if not text_content:
                    text_content = json.dumps(content_to_process, ensure_ascii=False)
            
            # [OPTIMIZATION] Calculate Hash
            current_hash = hashlib.sha256(text_content.encode('utf-8')).hexdigest()
            
            # [OPTIMIZATION] Check comparison with existing chunks
            if not force_reprocess:
                existing_chunk = conn.execute(
                    select(generated_content_chunks.c.metadata)
                    .where(generated_content_chunks.c.course_content_id == course_content_id)
                    .limit(1)
                ).first()
                
                if existing_chunk and existing_chunk.metadata:
                    meta = existing_chunk.metadata
                    # Handle if driver returns str for JSONB
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except:
                            meta = {}
                            
                    if meta.get("source_hash") == current_hash:
                        print(f"Skipping ingestion for {course_content_id}: Content hash unchanged.")
                        return {"status": "skipped", "reason": "hash_unchanged"}

            # 3. Chunking
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.rag.chunk_size,
                chunk_overlap=settings.rag.chunk_overlap,
                separators=["\n\n", "##", "\n", "。", "！", "？", ".", "!", "?", " ", ""] # Added ## for markdown sections
            )
            chunks = splitter.split_text(text_content)
            
            if not chunks:
                 print(f"Warning: No text chunks generated for content {course_content_id}")
                 return {"status": "skipped", "reason": "no_chunks_generated"} 
                 
            # 4. Generate Embeddings
            from backend.app.services.embedding_service import embedding_service
            embeddings, usage = embedding_service.create_embeddings(chunks)
            
            prompt_tokens = usage.get("total_tokens", 0)
            model_name = usage.get("model", "text-embedding-3-small")
            estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, 0)
            
            # 5. Transaction: Delete Old -> Insert New
            conn.execute(
                delete(generated_content_chunks)
                .where(generated_content_chunks.c.course_content_id == course_content_id)
            )
            
            # [NEW] Prepare rich metadata for storage
            # We use content_to_process which is the CLEAN version (no retrieved_text_chunks, no base64)
            # We merge it with system fields
            rich_metadata = {
                "source": "generated", 
                "title": title,
                "document_name": title,
                "document_id": course_content_id, # Link back to course_contents
                "type": content_type,
                "source_hash": current_hash,
                "unit_id": unit_id,
                "uploaded_at": get_now_taipei().strftime("%Y-%m-%d")
            }
            if isinstance(content_to_process, dict):
                # [OPTIMIZATION] Strip heavy fields (retrieved chunks, base64) from metadata
                # We only want to store the generated summary structure, not the full source copies.
                # The sources are already available in 'course_contents' via 'retrieved_text_chunks' column.
                clean_metadata = content_to_process.copy()
                
                # Remove full source chunks
                if "retrieved_text_chunks" in clean_metadata:
                    # Optionally extract source names for searchability
                    source_chunks = clean_metadata["retrieved_text_chunks"]
                    if source_chunks and isinstance(source_chunks, list):
                        sources = set()
                        for c in source_chunks:
                            meta = c.get("source_metadata") or {}
                            if meta.get("filename"): sources.add(meta["filename"])
                            elif meta.get("title"): sources.add(meta["title"])
                        if sources:
                            rich_metadata["related_sources"] = list(sources)
                    
                    del clean_metadata["retrieved_text_chunks"]
                
                # Remove raw content list if present (since we serialize it to text)
                # But keep it if it helps structure? Usually serialization is enough.
                # Keeping it is fine as long as it's not huge. Summaries are usually text.
                
                rich_metadata.update(clean_metadata)
            
            chunk_data = [
                {
                    "course_content_id": course_content_id,
                    "chunk_text": chunk,
                    "chunk_order": i,
                    "metadata": rich_metadata, # [MODIFIED] Store full structured content
                    "multimodal_metadata": multimodal_metadata, 
                    "embedding": embedding
                }
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
            ]
            
            if chunk_data:
                conn.execute(insert(generated_content_chunks), chunk_data)
                    
            print(f"Successfully ingested generated content {course_content_id} ({len(chunks)} chunks)")
            
            # [NEW] Return metrics for @log_task to capture
            return {
                "status": "success",
                "chunks_count": len(chunks),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "estimated_cost_usd": float(estimated_cost),
                "model_name": model_name
            }

    except Exception as e:
        logger.error(f"Error ingesting course content {course_content_id}: {e}")
        return {"status": "failed", "error": str(e)}