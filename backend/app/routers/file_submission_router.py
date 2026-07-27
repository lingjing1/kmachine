"""
File Submission Router: 檔案繳交作業 API
支援學生上傳檔案繳交、教師查看/下載/評分
"""
import os
import re
import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, List
import json
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from backend.app.utils.db_logger import engine
from backend.app.utils.auth_utils import get_current_user_id
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.config.settings import settings

router = APIRouter(prefix="/api", tags=["File Submissions"])

# ==================== Config ====================
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
STORAGE_BASE = Path(settings.upload_dir).parent / "uploads" / "file_submissions"


# ==================== Pydantic Models ====================

class SubmissionFile(BaseModel):
    name: str
    original_name: str
    path: str
    size: int
    type: str
    uploaded_at: str

class FileSubmissionResponse(BaseModel):
    id: int
    content_id: int
    user_id: int
    files: List[SubmissionFile] = []
    score: Optional[float] = None
    feedback: Optional[str] = None
    is_manual: bool = False
    submitted_at: str
    updated_at: Optional[str] = None


class TeacherFileSubmissionResponse(BaseModel):
    id: int
    content_id: int
    user_id: int
    student_name: str
    student_id: Optional[str] = None  # 學號
    files: List[SubmissionFile] = []
    score: Optional[float] = None
    feedback: Optional[str] = None
    is_manual: bool = False
    submitted_at: str
    updated_at: Optional[str] = None


class GradeRequest(BaseModel):
    score: float
    feedback: Optional[str] = None


# ==================== Helper Functions ====================

def sanitize_filename(filename: str) -> str:
    """清理檔名：移除危險字元，保留中文"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.strip()
    if not filename:
        filename = "unnamed_file"
    return filename


def _get_content_info(content_id: int) -> dict:
    """Get content info including course_id and unit_id for storage path."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT cc.id, cc.course_id, cc.unit_id, cc.assignment_type, cc.title, cc.end_time
            FROM course_contents cc
            WHERE cc.id = :content_id
        """), {"content_id": content_id}).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "course_id": row[1],
            "unit_id": row[2],
            "assignment_type": row[3],
            "title": row[4],
            "end_time": row[5],
        }


def _get_storage_dir(course_id: int, unit_id: int, content_id: int) -> Path:
    """Build storage path: file_submissions/{course_id}/{unit_id}/{content_id}/"""
    path = STORAGE_BASE / str(course_id) / str(unit_id or 0) / str(content_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ==================== Student Endpoints ====================

@router.post("/student/file-submissions/{content_id}/upload", response_model=FileSubmissionResponse)
async def upload_file_submission(
    content_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    學生上傳檔案繳交（UPSERT：重新上傳會覆蓋舊檔案）
    """
    # 1. Validate content exists and is file_upload type
    content_info = await run_in_db_pool(_get_content_info, content_id)
    if not content_info:
        raise HTTPException(status_code=404, detail="作業不存在")
    if content_info["assignment_type"] != "file_upload":
        raise HTTPException(status_code=400, detail="此作業不是檔案繳交類型")

    # 3. Check deadline (end_time)
    end_time = content_info.get("end_time")
    if end_time is not None:
        now = get_now_taipei()
        if now > end_time:
            raise HTTPException(status_code=403, detail="繳交截止時間已過，無法繼續上傳")

    # 4. Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="檔案過大，最大允許 50MB")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="檔案為空")

    # 3. Save file to disk
    original_filename = file.filename or "unnamed"
    safe_filename = sanitize_filename(original_filename)
    storage_dir = _get_storage_dir(
        content_info["course_id"],
        content_info["unit_id"],
        content_id
    )
    # Use timestamp to allow multiple files with same name
    timestamp = get_now_taipei().strftime("%Y%m%d%H%M%S")
    stored_filename = f"{current_user_id}_{timestamp}_{safe_filename}"
    file_path = storage_dir / stored_filename

    def _save_file():
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    try:
        await run_in_db_pool(_save_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"檔案儲存失敗：{str(e)}")

    # 4. UPSERT into submissions_assignment using jsonb_insert or manual merge
    file_mime = file.content_type or "application/octet-stream"
    new_file_item = {
        "name": stored_filename,
        "original_name": original_filename,
        "path": str(file_path),
        "size": file_size,
        "type": file_mime,
        "uploaded_at": get_now_taipei().isoformat()
    }

    def _upsert_submission_multiple(uid, cid, file_item):
        with engine.connect() as conn:
            # Check if submission exists
            existing = conn.execute(text("""
                SELECT id, files FROM submissions_assignment
                WHERE user_id = :uid AND content_id = :cid
            """), {"uid": uid, "cid": cid}).fetchone()

            if existing:
                sub_id = existing[0]
                existing_files = existing[1] if existing[1] else []
                if isinstance(existing_files, str):
                    existing_files = json.loads(existing_files)
                
                existing_files.append(file_item)

                conn.execute(text("""
                    UPDATE submissions_assignment
                    SET files = :files, updated_at = :now
                    WHERE id = :sid
                """), {
                    "files": json.dumps(existing_files),
                    "sid": sub_id,
                    "now": get_now_taipei()
                })
            else:
                # Insert new
                result = conn.execute(text("""
                    INSERT INTO submissions_assignment
                        (user_id, content_id, files)
                    VALUES (:uid, :cid, :files)
                    RETURNING id
                """), {
                    "uid": uid, "cid": cid,
                    "files": json.dumps([file_item])
                })
                sub_id = result.scalar()
            conn.commit()

            # Return full record
            row = conn.execute(text("""
                SELECT id, content_id, user_id, files, score, feedback, submitted_at, updated_at, is_manual
                FROM submissions_assignment WHERE id = :sid
            """), {"sid": sub_id}).fetchone()
            return row

    row = await run_in_db_pool(_upsert_submission_multiple, current_user_id, content_id, new_file_item)

    files_list = row[3] if row[3] else []
    if isinstance(files_list, str):
        files_list = json.loads(files_list)

    return FileSubmissionResponse(
        id=row[0], content_id=row[1], user_id=row[2],
        files=files_list, score=row[4], feedback=row[5],
        submitted_at=row[6].isoformat() if row[6] else "",
        updated_at=row[7].isoformat() if row[7] else None,
        is_manual=bool(row[8]) if row[8] is not None else False,
    )

@router.delete("/student/file-submissions/{content_id}/files/{filename}", response_model=FileSubmissionResponse)
async def delete_file_from_submission(
    content_id: int,
    filename: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    學生刪除已繳交的單一檔案
    """
    def _delete_file(uid, cid, fname):
        with engine.connect() as conn:
            existing = conn.execute(text("""
                SELECT id, files FROM submissions_assignment
                WHERE user_id = :uid AND content_id = :cid
            """), {"uid": uid, "cid": cid}).fetchone()

            if not existing or not existing[1]:
                return None, "找不到繳交紀錄或檔案"

            sub_id = existing[0]
            existing_files = existing[1]
            if isinstance(existing_files, str):
                existing_files = json.loads(existing_files)

            # Find file to delete
            filtered_files = [f for f in existing_files if f['name'] != fname]
            deleted_file = next((f for f in existing_files if f['name'] == fname), None)

            if len(filtered_files) == len(existing_files):
                return None, "找不到指定檔案"

            # Delete from disk
            if deleted_file:
                try:
                    p = Path(deleted_file['path'])
                    if p.exists():
                        p.unlink()
                except:
                    pass

            # Update DB
            conn.execute(text("""
                UPDATE submissions_assignment
                SET files = :files, updated_at = :now
                WHERE id = :sid
            """), {
                "files": json.dumps(filtered_files),
                "sid": sub_id,
                "now": get_now_taipei()
            })
            conn.commit()

            row = conn.execute(text("""
                SELECT id, content_id, user_id, files, score, feedback, submitted_at, updated_at, is_manual
                FROM submissions_assignment WHERE id = :sid
            """), {"sid": sub_id}).fetchone()
            return row, None

    row, error = await run_in_db_pool(_delete_file, current_user_id, content_id, filename)
    if error:
        raise HTTPException(status_code=404, detail=error)

    files_list = row[3] if row[3] else []
    if isinstance(files_list, str):
        files_list = json.loads(files_list)

    return FileSubmissionResponse(
        id=row[0], content_id=row[1], user_id=row[2],
        files=files_list, score=row[4], feedback=row[5],
        submitted_at=row[6].isoformat() if row[6] else "",
        updated_at=row[7].isoformat() if row[7] else None,
        is_manual=bool(row[8]) if row[8] is not None else False,
    )


@router.get("/student/file-submissions/{content_id}", response_model=Optional[FileSubmissionResponse])
async def get_my_file_submission(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    學生查看自己的繳交狀態
    """
    def _get_submission(uid, cid):
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT id, content_id, user_id, files,
                       score, feedback, submitted_at, updated_at, is_manual
                FROM submissions_assignment
                WHERE user_id = :uid AND content_id = :cid
            """), {"uid": uid, "cid": cid}).fetchone()
            return row

    row = await run_in_db_pool(_get_submission, current_user_id, content_id)
    if not row:
        return None

    files_list = row[3] if row[3] else []
    if isinstance(files_list, str):
        files_list = json.loads(files_list)

    return FileSubmissionResponse(
        id=row[0], content_id=row[1], user_id=row[2],
        files=files_list, score=row[4], feedback=row[5],
        submitted_at=row[6].isoformat() if row[6] else "",
        updated_at=row[7].isoformat() if row[7] else None,
        is_manual=bool(row[8]) if row[8] is not None else False,
    )
@router.get("/student/file-submissions/{content_id}/download/{filename}")
async def download_student_submitted_file(
    content_id: int,
    filename: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    學生下載自己繳交的檔案
    """
    def _get_my_file_info(uid, cid, fname):
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT id, files FROM submissions_assignment 
                WHERE user_id = :uid AND content_id = :cid
            """), {"uid": uid, "cid": cid}).fetchone()
            if not row or not row[1]: return None
            
            files_list = row[1]
            if isinstance(files_list, str): files_list = json.loads(files_list)
            return next((f for f in files_list if f['name'] == fname), None)

    file_info = await run_in_db_pool(_get_my_file_info, current_user_id, content_id, filename)
    if not file_info:
        raise HTTPException(status_code=404, detail="檔案不存在或無權訪問")

    file_path = Path(file_info['path'])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案實體不存在於伺服器")

    return FileResponse(
        path=str(file_path),
        filename=file_info['original_name'],
        media_type=file_info['type']
    )


# ==================== Teacher Endpoints ====================

@router.get("/teacher/file-submissions/{content_id}", response_model=List[TeacherFileSubmissionResponse])
async def list_file_submissions(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    教師查看所有學生的檔案繳交（含學生資訊）
    """
    def _list_submissions(cid):
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT sa.id, sa.content_id, sa.user_id,
                       u.full_name, sp.student_id,
                       sa.files, sa.score, sa.feedback,
                       sa.submitted_at, sa.updated_at, sa.is_manual
                FROM submissions_assignment sa
                JOIN users u ON sa.user_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE sa.content_id = :cid
                ORDER BY sa.submitted_at DESC
            """), {"cid": cid}).fetchall()
            return rows

    rows = await run_in_db_pool(_list_submissions, content_id)

    res = []
    for r in rows:
        files_list = r[5] if r[5] else []
        if isinstance(files_list, str):
            files_list = json.loads(files_list)
        
        res.append(TeacherFileSubmissionResponse(
            id=r[0], content_id=r[1], user_id=r[2],
            student_name=r[3] or "未知", student_id=r[4],
            files=files_list, score=r[6], feedback=r[7],
            submitted_at=r[8].isoformat() if r[8] else "",
            updated_at=r[9].isoformat() if r[9] else None,
            is_manual=bool(r[10]) if r[10] is not None else False,
        ))
    return res


@router.get("/teacher/file-submissions/download/{submission_id}")
async def download_file_submission(
    submission_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    教師下載單一學生繳交檔案
    """
    def _get_file_info(sid):
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT files FROM submissions_assignment WHERE id = :sid
            """), {"sid": sid}).fetchone()
            return row

    row = await run_in_db_pool(_get_file_info, submission_id)
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="繳交紀錄不存在")

    files_list = row[0]
    if isinstance(files_list, str):
        files_list = json.loads(files_list)
    
    if not files_list:
        raise HTTPException(status_code=404, detail="無繳交檔案")

    # Download only the first file for this simple endpoint (legacy support)
    file_info = files_list[0]
    file_path = Path(file_info['path'])
    
    # Robust path resolution for environment mismatches
    if not file_path.exists():
        path_str = str(file_path)
        if 'file_submissions' in path_str:
            relative_part = path_str.split('file_submissions', 1)[1].lstrip('/')
            alternative_path = STORAGE_BASE / relative_part
            if alternative_path.exists():
                file_path = alternative_path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"檔案不存在於伺服器: {file_info.get('original_name')}")

    return FileResponse(
        path=str(file_path),
        filename=file_info['original_name'] or "download",
        media_type=file_info['type'] or "application/octet-stream"
    )

@router.get("/teacher/file-submissions/download-file/{submission_id}/{filename}")
async def download_specific_file_submission(
    submission_id: int,
    filename: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    下載指定繳交紀錄中的特定檔案
    """
    def _get_file_info(sid, fname):
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT files FROM submissions_assignment WHERE id = :sid
            """), {"sid": sid}).fetchone()
            if not row or not row[0]: return None
            files_list = row[0]
            if isinstance(files_list, str): files_list = json.loads(files_list)
            return next((f for f in files_list if f['name'] == fname), None)

    file_info = await run_in_db_pool(_get_file_info, submission_id, filename)
    if not file_info:
        raise HTTPException(status_code=404, detail="檔案資訊不存在於資料庫")

    file_path = Path(file_info['path'])
    
    # Robust path resolution for environment mismatches
    if not file_path.exists():
        path_str = str(file_path)
        if 'file_submissions' in path_str:
            relative_part = path_str.split('file_submissions', 1)[1].lstrip('/')
            alternative_path = STORAGE_BASE / relative_part
            if alternative_path.exists():
                file_path = alternative_path

    if not file_path.exists():
        # Log the missing file for debugging
        print(f"ERROR: File not found on disk: {file_path} (Original stored path: {file_info['path']})")
        raise HTTPException(status_code=404, detail=f"檔案實體不存在於伺服器: {file_info.get('original_name')}")

    return FileResponse(
        path=str(file_path),
        filename=file_info['original_name'],
        media_type=file_info['type']
    )


@router.get("/teacher/file-submissions/{content_id}/download-all")
async def download_all_file_submissions(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    教師打包下載所有學生繳交 (ZIP)
    """
    def _get_all_files(cid):
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT sa.files, u.full_name, sp.student_id
                FROM submissions_assignment sa
                JOIN users u ON sa.user_id = u.id
                LEFT JOIN student_profiles sp ON sp.user_id = u.id
                WHERE sa.content_id = :cid
            """), {"cid": cid}).fetchall()
            return rows

    rows = await run_in_db_pool(_get_all_files, content_id)
    if not rows:
        raise HTTPException(status_code=404, detail="沒有學生繳交")

    # Get content title for zip filename
    content_info = await run_in_db_pool(_get_content_info, content_id)
    zip_name = sanitize_filename(content_info["title"]) if content_info else f"submissions_{content_id}"

    # Create ZIP in temp file
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for row in rows:
                files_json = row[0]
                if not files_json: continue
                if isinstance(files_json, str): files_json = json.loads(files_json)
                
                student_id = row[2] or "unknown"
                student_name = sanitize_filename(row[1] or "unknown")
                
                for f_info in files_json:
                    fpath = Path(f_info['path'])
                    if fpath.exists():
                        original_name = f_info['original_name'] or fpath.name
                        # Include filename prefix or folder to handle multiple files
                        arc_name = f"{student_id}_{student_name}/{original_name}"
                        zf.write(fpath, arc_name)

        return FileResponse(
            path=temp_zip.name,
            filename=f"{zip_name}.zip",
            media_type="application/zip",
            background=None  # Let cleanup happen after response
        )
    except Exception as e:
        os.unlink(temp_zip.name)
        raise HTTPException(status_code=500, detail=f"打包失敗：{str(e)}")


@router.put("/teacher/file-submissions/{submission_id}/grade", response_model=FileSubmissionResponse)
async def grade_file_submission(
    submission_id: int,
    grade_req: GradeRequest,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    教師對檔案繳交打分數
    """
    def _grade_submission(sid, score, feedback):
        with engine.connect() as conn:
            # Verify submission exists
            existing = conn.execute(text("""
                SELECT id FROM submissions_assignment WHERE id = :sid
            """), {"sid": sid}).fetchone()
            if not existing:
                return None

            conn.execute(text("""
                UPDATE submissions_assignment
                SET score = :score, feedback = :feedback, updated_at = :now, is_manual = TRUE
                WHERE id = :sid
            """), {"sid": sid, "score": score, "feedback": feedback, "now": get_now_taipei()})
            conn.commit()

            row = conn.execute(text("""
                SELECT id, content_id, user_id, files, score, feedback, submitted_at, updated_at, is_manual
                FROM submissions_assignment WHERE id = :sid
            """), {"sid": sid}).fetchone()
            return row

    row = await run_in_db_pool(_grade_submission, submission_id, grade_req.score, grade_req.feedback)
    if not row:
        raise HTTPException(status_code=404, detail="繳交紀錄不存在")

    files_list = row[3] if row[3] else []
    if isinstance(files_list, str):
        files_list = json.loads(files_list)

    return FileSubmissionResponse(
        id=row[0], content_id=row[1], user_id=row[2],
        files=files_list, score=row[4], feedback=row[5],
        submitted_at=row[6].isoformat() if row[6] else "",
        updated_at=row[7].isoformat() if row[7] else None,
        is_manual=bool(row[8]) if row[8] is not None else False,
    )
