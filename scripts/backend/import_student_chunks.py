"""
Import Student Document Chunks
將 scripts/extracted_content/ 中的教材內容處理後存入資料庫
"""
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from sqlalchemy import create_engine, text
from openai import OpenAI
from dotenv import load_dotenv
import tiktoken

# Load environment variables
load_dotenv()

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Initialize
engine = create_engine(DATABASE_URL)
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0, max_retries=3)  # 提高穩定性
tokenizer = tiktoken.get_encoding("cl100k_base")

def load_unit_mapping() -> Dict[str, str]:
    """載入 PDF 前綴 -> Unit 名稱映射"""
    with open("scripts/unit_mapping.json", "r", encoding="utf-8") as f:
        mapping_list = json.load(f)
    return {item["from_unit"]: item["to_unit"] for item in mapping_list}

def load_knowledge_points() -> Dict[str, List[str]]:
    """載入標準知識點列表，返回 {chapter: [kp_list]}"""
    with open("scripts/knowledge_points.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["chapter"]: item["Knowledge_points"] for item in data}

def validate_kp_name(kp_name: str, unit_name: str, kp_mapping: Dict[str, List[str]]) -> Optional[str]:
    """驗證並標準化知識點名稱
    
    Args:
        kp_name: 從檔名提取的知識點名稱
        unit_name: Unit 名稱（用於定位到正確的 chapter）
        kp_mapping: 標準知識點映射
    
    Returns:
        標準化的知識點名稱，如果找不到則返回 None
    """
    if unit_name not in kp_mapping:
        return None
    
    kp_list = kp_mapping[unit_name]
    
    # 精確匹配
    if kp_name in kp_list:
        return kp_name
    
    # 模糊匹配（去除空格、全半形）
    normalized_input = kp_name.replace(" ", "").replace("　", "")
    for standard_kp in kp_list:
        normalized_standard = standard_kp.replace(" ", "").replace("　", "")
        if normalized_input == normalized_standard:
            return standard_kp
    
    # 找不到匹配
    return None

def get_unit_and_kp_id(unit_name: str, kp_name: str, course_id: int = 3) -> Dict:
    """根據 unit 和 knowledge_point 名稱查詢 ID"""
    with engine.connect() as conn:
        # Query unit
        unit_result = conn.execute(
            text("SELECT id FROM course_units WHERE course_id = :cid AND name = :name"),
            {"cid": course_id, "name": unit_name}
        ).fetchone()
        
        if not unit_result:
            return {"unit_id": None, "knowledge_point_id": None, "error": f"Unit not found: {unit_name}"}
        
        unit_id = unit_result[0]
        
        # Query knowledge_point
        kp_result = conn.execute(
            text("SELECT id FROM knowledge_points WHERE course_id = :cid AND unit_id = :uid AND name = :name"),
            {"cid": course_id, "uid": unit_id, "name": kp_name}
        ).fetchone()
        
        kp_id = kp_result[0] if kp_result else None
        
        return {"unit_id": unit_id, "knowledge_point_id": kp_id}

def parse_filename(filename: str) -> Dict:
    """解析檔名，提取 PDF 前綴和知識點名稱
    
    格式：{PDF前綴}_{知識點名稱}_content.txt
    例如：A_機器學習-監督式學習_監督式學習的定義_content.txt
    
    pdf_prefix = 前兩段 (A_機器學習-監督式學習)
    kp_name = 剩下的全部 (監督式學習的定義)
    """
    name = filename.replace("_content.txt", "")
    parts = name.split("_")
    
    if len(parts) < 3:
        return {"pdf_prefix": None, "kp_name": None, "error": f"Invalid filename format: {filename}"}
    
    # 前兩段組成 pdf_prefix：A_機器學習-監督式學習
    pdf_prefix = "_".join(parts[:2])
    # 剩下的全部組成 kp_name（避免 kp 名稱本身也含 _）
    kp_name = "_".join(parts[2:])
    
    return {"pdf_prefix": pdf_prefix, "kp_name": kp_name}

def extract_page_numbers(content: str) -> str:
    """從內容中提取頁碼資訊"""
    # 匹配 "頁碼：7, 8, 9, 10" 格式
    match = re.search(r"頁碼：([\d\s,]+)", content)
    if match:
        return match.group(1).strip()
    return ""

def smart_chunk_by_page(content: str, max_tokens: int = 1000, overlap: int = 200) -> List[Dict]:
    """智能切分：優先保留完整頁面內容，並實作 overlap
    
    策略：
    1. 按 "=== 第 X 頁 ===" 分割頁面
    2. 如果單頁超過 max_tokens，則在頁內切分
    3. 如果單頁小於 max_tokens，嘗試合併下一頁
    4. 實作 token-level overlap（保留前一段的尾部作為下一段開頭）
    """
    # 分割成各頁
    page_pattern = r"(=== 第 \d+ 頁 ===)"
    parts = re.split(page_pattern, content)
    
    pages = []
    i = 0
    while i < len(parts):
        if re.match(page_pattern, parts[i]):
            page_header = parts[i]
            page_content = parts[i+1] if i+1 < len(parts) else ""
            pages.append({"header": page_header, "content": page_content})
            i += 2
        else:
            i += 1
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    overlap_text = ""  # 保留上一段的尾部
    
    for page in pages:
        page_text = page["header"] + "\n" + page["content"]
        page_tokens = len(tokenizer.encode(page_text))
        
        if page_tokens > max_tokens:
            # 頁面太大，需要切分
            if current_chunk:
                chunks.append(current_chunk)
                # 提取尾部作為 overlap
                overlap_text = _extract_overlap_tail(current_chunk, overlap)
                current_chunk = ""
                current_tokens = 0
            
            # 在頁面內部切分
            sentences = page_text.split("\n")
            temp_chunk = overlap_text  # 從 overlap 開始
            temp_tokens = len(tokenizer.encode(temp_chunk)) if temp_chunk else 0
            
            for sentence in sentences:
                sentence_tokens = len(tokenizer.encode(sentence))
                if temp_tokens + sentence_tokens > max_tokens:
                    if temp_chunk:
                        chunks.append(temp_chunk)
                        overlap_text = _extract_overlap_tail(temp_chunk, overlap)
                    temp_chunk = overlap_text + sentence + "\n"
                    temp_tokens = len(tokenizer.encode(temp_chunk))
                else:
                    temp_chunk += sentence + "\n"
                    temp_tokens += sentence_tokens
            
            if temp_chunk:
                current_chunk = temp_chunk
                current_tokens = temp_tokens
        
        else:
            # 嘗試合併頁面
            if current_tokens + page_tokens <= max_tokens:
                current_chunk += page_text + "\n"
                current_tokens += page_tokens
            else:
                # 儲存當前 chunk，開始新的（含 overlap）
                if current_chunk:
                    chunks.append(current_chunk)
                    overlap_text = _extract_overlap_tail(current_chunk, overlap)
                current_chunk = overlap_text + page_text + "\n"
                current_tokens = len(tokenizer.encode(current_chunk))
    
    # 儲存最後一個 chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return [{"text": chunk, "tokens": len(tokenizer.encode(chunk))} for chunk in chunks]

def _extract_overlap_tail(text: str, overlap_tokens: int) -> str:
    """從文本尾部提取 overlap_tokens 個 token 的內容"""
    if not text or overlap_tokens <= 0:
        return ""
    
    tokens = tokenizer.encode(text)
    if len(tokens) <= overlap_tokens:
        return text
    
    # 取最後 overlap_tokens 個 token
    overlap_token_ids = tokens[-overlap_tokens:]
    return tokenizer.decode(overlap_token_ids)

def get_embedding(text: str) -> Optional[List[float]]:
    """生成 Embedding"""
    if not text or not text.strip():
        return None
    try:
        response = openai_client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"❌ Embedding 生成失敗: {e}")
        return None

def _to_pgvector_str(vec: List[float]) -> str:
    """轉換為 pgvector 格式"""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"

def insert_chunks(course_id: int, unit_id: int, kp_id: Optional[int], 
                  source_filename: str, page_numbers: str, chunks: List[Dict]):
    """批量插入 Chunks"""
    with engine.begin() as conn:
        for idx, chunk in enumerate(chunks, start=1):
            embedding = get_embedding(chunk["text"])
            if not embedding:
                print(f"⚠️  Chunk {idx} embedding 失敗，跳過")
                continue
            
            conn.execute(
                text("""
                    INSERT INTO student_document_chunks 
                    (course_id, unit_id, knowledge_point_id, source_filename, 
                     chunk_order, chunk_text, embedding, page_numbers, metadata)
                    VALUES 
                    (:course_id, :unit_id, :kp_id, :filename, :order, :text, 
                     (:embedding)::vector, :pages, :metadata)
                """),
                {
                    "course_id": course_id,
                    "unit_id": unit_id,
                    "kp_id": kp_id,
                    "filename": source_filename,
                    "order": idx,
                    "text": chunk["text"],
                    "embedding": _to_pgvector_str(embedding),
                    "pages": page_numbers,
                    "metadata": json.dumps({"tokens": chunk["tokens"]}, ensure_ascii=False)
                }
            )

def process_all_files():
    """處理所有教材檔案"""
    extracted_dir = Path("scripts/extracted_content")
    unit_mapping = load_unit_mapping()
    kp_mapping = load_knowledge_points()
    
    files = sorted(extracted_dir.glob("*_content.txt"))  # 只抓 _content.txt 避免誤抓其他檔案
    print(f"📂 找到 {len(files)} 個教材檔案\n")
    
    stats = {"success": 0, "failed": 0, "total_chunks": 0, "kp_mismatch": 0}
    
    for file in files:
        print(f"📄 處理: {file.name}")
        
        # 解析檔名
        parsed = parse_filename(file.name)
        if "error" in parsed:
            print(f"   ❌ {parsed['error']}")
            stats["failed"] += 1
            continue
        
        # 映射 Unit
        unit_name = unit_mapping.get(parsed["pdf_prefix"])
        if not unit_name:
            print(f"   ❌ 無法映射 Unit: {parsed['pdf_prefix']}")
            stats["failed"] += 1
            continue
        
        # 驗證知識點名稱
        validated_kp = validate_kp_name(parsed["kp_name"], unit_name, kp_mapping)
        if not validated_kp:
            print(f"   ⚠️  知識點名稱不匹配: '{parsed['kp_name']}'")
            print(f"      可用的知識點: {kp_mapping.get(unit_name, [])}")
            stats["kp_mismatch"] += 1
            # 繼續使用原始名稱，但標記為警告
            validated_kp = parsed["kp_name"]
        
        # 讀取內容
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 提取頁碼
        page_numbers = extract_page_numbers(content)
        
        # 查詢 IDs
        ids = get_unit_and_kp_id(unit_name, validated_kp)
        if "error" in ids:
            print(f"   ❌ {ids['error']}")
            stats["failed"] += 1
            continue
        
        # 切分 Chunks
        chunks = smart_chunk_by_page(content, max_tokens=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        print(f"   ✂️  切分為 {len(chunks)} 個 Chunks")
        
        # 插入資料庫
        try:
            insert_chunks(
                course_id=3,
                unit_id=ids["unit_id"],
                kp_id=ids["knowledge_point_id"],
                source_filename=file.name,
                page_numbers=page_numbers,
                chunks=chunks
            )
            stats["success"] += 1
            stats["total_chunks"] += len(chunks)
            print(f"   ✅ 成功插入 {len(chunks)} 個 Chunks\n")
        except Exception as e:
            print(f"   ❌ 插入失敗: {e}\n")
            stats["failed"] += 1
    
    print("\n" + "="*60)
    print(f"✅ 處理完成！")
    print(f"   成功: {stats['success']} 個檔案")
    print(f"   失敗: {stats['failed']} 個檔案")
    print(f"   知識點不匹配警告: {stats['kp_mismatch']} 個檔案")
    print(f"   總 Chunks: {stats['total_chunks']}")
    print("="*60)

if __name__ == "__main__":
    process_all_files()
