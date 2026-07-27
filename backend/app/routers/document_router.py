"""
Document Serving Router: 學生端文檔訪問
提供學生查看引用來源的原始文檔
"""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# 文檔存儲路徑 
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STORAGE_DIR = BASE_DIR / "backend" / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"


def find_document_by_name(source_filename: str) -> Optional[Path]:
    """
    在 uploads 目錄中查找文檔
    文件存儲格式: {sha256_hash}_{original_filename}
    支援擴充名回退 (例如: 請求 .pdf 但只有 .pptx)
    """
    # 1. 精確匹配
    for filepath in UPLOADS_DIR.iterdir():
        if filepath.is_file() and filepath.name.endswith(f"_{source_filename}"):
            return filepath
            
    # 2. 模糊匹配 (如果請求的是 .pdf，嘗試尋找同名的其他格式)
    if source_filename.lower().endswith('.pdf'):
        base_name = source_filename.rsplit('.', 1)[0]
        # 常見的原始格式
        fallbacks = ['.pptx', '.ppt', '.docx', '.doc', '.png', '.jpg', '.jpeg']
        for filepath in UPLOADS_DIR.iterdir():
            if not filepath.is_file():
                continue
            for ext in fallbacks:
                if filepath.name.endswith(f"_{base_name}{ext}"):
                    return filepath

    return None


@router.get("/by-name/{source_filename:path}")
async def serve_document_by_name(
    source_filename: str,
    inline: bool = Query(True, description="是否在瀏覽器內預覽（PDF）")
):
    """
    根據引用來源文件名提供文檔
    主要用於學生查看引用來源的原始 PDF
    
    Example: /api/documents/by-name/1132 0 CA CourseOverview.pdf
    """
    # 查找文件
    file_path = find_document_by_name(source_filename)
    
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"找不到文件: {source_filename}"
        )
    
    # 設置 media type
    file_ext = file_path.suffix.lower()
    media_type_map = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    
    media_type = media_type_map.get(file_ext, "application/octet-stream")
    
    # 設置 headers
    disposition_type = 'inline' if inline else 'attachment'
    
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=source_filename,
        content_disposition_type=disposition_type
    )

