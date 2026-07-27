import tiktoken
from typing import List, Tuple, Dict, Any
from backend.app.services.document_loader import Page
from backend.app.config.settings import settings

def chunk_document(
    pages: List[Page],
    chunk_size: int,
    chunk_overlap: int,
    file_name: str,
    uploader_id: int
) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """
    使用滑動視窗策略將文檔切分成 chunks，並確保不超過 OpenAI Embedding 模型 Token 限制。
    """
    
    # 0. 初始化 Token 計算器
    try:
        encoding = tiktoken.get_encoding("cl100k_base") # text-embedding-3-small 使用此編碼
    except Exception:
        encoding = None
        print("Warning: tiktoken not found, using character length only.")

    # 分隔符優先級
    SEPARATORS = ["</圖片描述>", "\n\n", "\n", "。", "！", "？", ". ", " "]
    
    # 1. 建立完整文字和映射
    full_text = ""
    char_to_page_map = []
    char_to_image_map = []
    page_code_flags = {}
    
    total_pages_with_content = 0
    for page in pages:
        page_text = page.text_for_chunking
        if not page_text:
            continue
        
        total_pages_with_content += 1
        start_index = len(full_text)
        full_text += page_text + "\n\n"
        end_index = len(full_text)
        
        # 映射字元到頁碼
        for i in range(start_index, end_index):
            char_to_page_map.append(page.page_number)
        
        # 記錄頁面程式碼標記
        mm_meta = getattr(page, 'multimodal_metadata', None)
        if mm_meta:
            page_code_flags[page.page_number] = mm_meta.get('contains_code', False)
        
        # 映射圖片位置
        if mm_meta and mm_meta.get('images'):
            for img in mm_meta['images']:
                absolute_pos = start_index + img['position']
                char_to_image_map.append((absolute_pos, img, page.page_number))
    
    if not full_text:
        return []
    
    print(f"Splitting full_text of length {len(full_text)} characters from {total_pages_with_content} pages.")
    
    # 2. 簡化的滑動視窗切分
    chunks_with_metadata = []
    start_idx = 0
    
    # 安全限制：OpenAI Embedding 限制是 8192 tokens
    # 我們在這裡設定一個較保守的上限，如果 token 數超過此值，強制進一步切分
    MAX_TOKENS = 7500 

    while start_idx < len(full_text):
        # 計算結束位置
        end_idx = min(start_idx + chunk_size, len(full_text))
        
        # 如果不是最後一個 chunk，嘗試在分隔符處切分
        if end_idx < len(full_text):
            search_from = max(start_idx, end_idx - 300)
            search_region = full_text[search_from:end_idx]
            
            best_split = None
            for sep in SEPARATORS:
                if sep in search_region:
                    pos = search_region.rfind(sep)
                    if pos != -1:
                        best_split = search_from + pos + len(sep)
                        break
            
            if best_split and best_split > start_idx:
                end_idx = best_split
        
        # 提取 chunk 文字
        chunk_text = full_text[start_idx:end_idx].strip()
        
        if chunk_text:
            # ✅ Token 檢查與二次切分 (如果 Token 數超過限制)
            if encoding:
                token_count = len(encoding.encode(chunk_text))
                if token_count > MAX_TOKENS:
                    print(f"⚠️ Chunk too large ({token_count} tokens), emergency splitting...")
                    # 如果單個 chunk 已經超過限制，我們就均分它
                    # 這裡採用簡單的字元比例切割
                    ratio = MAX_TOKENS / token_count
                    safe_len = int(len(chunk_text) * ratio * 0.9) # 留 10% 餘裕
                    end_idx = start_idx + safe_len
                    chunk_text = full_text[start_idx:end_idx].strip()
                    print(f"   Emergency split result length: {len(chunk_text)} chars")

            # 確定頁碼範圍
            page_numbers = []
            if start_idx < len(char_to_page_map) and end_idx <= len(char_to_page_map):
                start_page = char_to_page_map[start_idx]
                end_page = char_to_page_map[min(end_idx - 1, len(char_to_page_map) - 1)]
                page_numbers = sorted(list(set(range(start_page, end_page + 1))))
            
            # 確定包含的圖片
            chunk_images = []
            for img_pos, img_data, img_page in char_to_image_map:
                if start_idx <= img_pos < end_idx:
                    relative_pos = img_pos - start_idx
                    img_entry = {
                        "position": relative_pos,
                        "vision_description": img_data.get("vision_description", ""),
                        "vision_tokens": img_data.get("vision_tokens", 0),
                        "vision_cost": img_data.get("vision_cost", 0.0)
                    }
                    if "image_path" in img_data:
                        img_entry["image_path"] = img_data["image_path"]
                    if "base64" in img_data:
                        img_entry["base64"] = img_data["base64"]
                    
                    chunk_images.append(img_entry)
            
            # 確定是否包含程式碼
            chunk_contains_code = any(
                page_code_flags.get(page_num, False)
                for page_num in page_numbers
            )
            
            # 構建 metadata
            page_meta = {"page_numbers": page_numbers}
            mm_meta = {
                "images": chunk_images,
                "contains_code": chunk_contains_code
            }
            
            chunks_with_metadata.append((chunk_text, page_meta, mm_meta))
        
        # 移動到下一個位置
        min_advance = max(chunk_size - chunk_overlap, 100)
        theoretical_next = start_idx + min_advance
        
        if theoretical_next < len(full_text):
            search_start = max(0, theoretical_next - 100)
            search_region = full_text[search_start:theoretical_next + 50]
            
            best_start = None
            for sep in SEPARATORS:
                pos = theoretical_next - search_start
                last_sep_pos = search_region.rfind(sep, 0, pos + 50)
                if last_sep_pos != -1:
                    absolute_pos = search_start + last_sep_pos + len(sep)
                    if absolute_pos > start_idx + 50:
                        best_start = absolute_pos
                        break
            
            if best_start:
                start_idx = best_start
            else:
                start_idx = theoretical_next
        else:
            start_idx = theoretical_next
        
        if start_idx >= len(full_text) - 1:
            break
    
    return chunks_with_metadata
