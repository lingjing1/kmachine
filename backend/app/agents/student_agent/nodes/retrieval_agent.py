"""
Retrieval Agent Node

職責：
1. 根據使用者查詢進行向量搜尋，檢索相關教材 chunks (使用正式 RAG 資料表)
2. 根據學生弱點關鍵字進行重排序（Reranking）
3. 過濾低品質結果

輸入（從 State 讀取）：
- user_query: 使用者問題
- weak_points: 弱點知識點列表（來自 Mastery Agent）
- course_id: 課程 ID

輸出（更新 State）：
- retrieved_chunks: 檢索到的教材片段
- chunk_sources: 來源資訊（含知識點名稱、單元名稱）
"""

from typing import Dict, List, Optional, Any
import os
import json
from openai import OpenAI
from sqlalchemy import text, select, Table
from backend.app.agents.student_agent.state import StudentAgentState
from backend.app.agents.student_agent.nodes.start_node import create_error
from backend.app.utils.db_logger import engine, metadata

# === OpenAI 客戶端設定 ===
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=10.0,   # 請求超時 10 秒
    max_retries=1   # 最多重試 1 次
)

EMBEDDING_MODEL = os.getenv("STUDENT_CHATBOT_EMBEDDING_MODEL", "text-embedding-3-small")

# === 資料表反射 ===
document_chunks = Table('document_chunks', metadata, autoload_with=engine)
uploaded_contents = Table('uploaded_contents', metadata, autoload_with=engine)
course_units = Table('course_units', metadata, autoload_with=engine)


def get_embedding(text: str) -> Optional[List[float]]:
    """生成文字的 Embedding 向量
    
    Args:
        text: 要生成向量的文字
        
    Returns:
        Optional[List[float]]: embedding 向量，失敗返回 None
    """
    if not text or not text.strip():
        return None
    try:
        response = openai_client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"生成 Embedding 時發生錯誤: {e}")
        return None


def _to_pgvector_str(vec: List[float]) -> str:
    """將 Python 向量轉換為 pgvector 格式字串"""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


# === RAG 核心邏輯 ===

def get_course_content_ids(course_id: int) -> Dict[int, Dict[str, Any]]:
    """取得課程教材的 unique_content_id 列表及其中繼資料 (如檔案名稱)
    
    Args:
        course_id: 課程 ID
        
    Returns:
        Dict[int, Dict]: Key 是 unique_content_id, Value 是包含 file_name 等資訊的 dict
    """
    # 路徑: uploaded_contents
    # 目的: 找出該課程所有可用的 unique_content_id
    
    # 這裡直接查詢 uploaded_contents 表
    # uploaded_contents 有 unique_content_id, course_id, file_name 等欄位
    
    sql = """
        SELECT 
            uc.unique_content_id,
            uc.file_name
        FROM uploaded_contents uc
        WHERE uc.course_id = :course_id
    """
    
    content_map = {}
    with engine.connect() as conn:
        results = conn.execute(text(sql), {"course_id": course_id}).fetchall()
        for row in results:
            uid = row.unique_content_id
            # 簡單映射 ID -> Info
            if uid not in content_map:
                content_map[uid] = {
                    "unit_name": "Course Material", # 暫無單元資訊，需從其他表關聯，目前先給預設值
                    "material_title": row.file_name
                }
                
    return content_map


def search_documents(
    query_embedding: List[float], 
    course_id: int, 
    limit: int = 20
) -> List[Dict]:
    """向量搜尋學生教材文件 (Production RAG Tables)
    
    1. 取得課程授權的 unique_content_ids
    2. 在 document_chunks 表中進行向量檢索 (Filtered by unique_content_id)
    3. 結合單元資訊回傳
    """
    
    # 步驟 1: 取得該課程的 content IDs
    content_map = get_course_content_ids(course_id)
    unique_content_ids = list(content_map.keys())
    
    if not unique_content_ids:
        print(f"Retrieval: Course {course_id} has no uploaded contents.")
        return []

    # 步驟 2: 向量搜尋 (使用 IN clause 和 Index)
    with engine.connect() as conn:
        sql = """
            SELECT 
                dc.id, 
                dc.chunk_text, 
                dc.unique_content_id,
                dc.metadata,
                GREATEST(0.0, 1 - (dc.embedding <=> (:embedding)::vector)) as similarity
            FROM document_chunks dc
            WHERE dc.unique_content_id IN :content_ids
            ORDER BY dc.embedding <=> (:embedding)::vector
            LIMIT :limit
        """
        
        # 轉換為 tuple 供 SQL 使用
        content_ids_tuple = tuple(unique_content_ids)
        
        results = conn.execute(text(sql), {
            "embedding": _to_pgvector_str(query_embedding),
            "content_ids": content_ids_tuple,
            "limit": int(limit)
        }).fetchall()
        
        # 步驟 3: 格式化結果，補回來來源資訊
        formatted_results = []
        for row in results:
            content_info = content_map.get(row.unique_content_id, {})
            metadata_obj = row.metadata if row.metadata else {}
            
            # 從 metadata 嘗試提取 page_numbers (通常是 list)
            page_nums = metadata_obj.get("page_numbers", [])
            if isinstance(page_nums, list):
                page_nums_str = ", ".join(map(str, page_nums))
            else:
                page_nums_str = str(page_nums)

            formatted_results.append({
                "chunk_id": row.id,
                "content": row.chunk_text,
                "source_filename": content_info.get("material_title", "Unknown"), # 使用 Course Material Title 作為檔名顯示
                "page_numbers": page_nums_str,
                "knowledge_point_name": None, # 目前 document_chunks 未直接關聯 KP，暫留空
                "unit_name": content_info.get("unit_name", "Unknown Unit"),
                "similarity": row.similarity,
                "unique_content_id": row.unique_content_id
            })
            
        return formatted_results


def detect_knowledge_point(query: str, course_id: int) -> Optional[int]:
    """使用 LLM 與語意判定最匹配的知識點 ID
    
    Args:
        query: 學生提問
        course_id: 課程 ID
        
    Returns:
        Optional[int]: 最匹配的 knowledge_point_id
    """
    try:
        # 1. 取得該課程所有知識點
        sql = """
            SELECT id, name FROM knowledge_points 
            WHERE course_id = :course_id
        """
        with engine.connect() as conn:
            kp_rows = conn.execute(text(sql), {"course_id": course_id}).fetchall()
            if not kp_rows:
                return None
            
            kp_list = [{"id": r.id, "name": r.name} for r in kp_rows]
            
        # 2. 準備 Prompt 給 LLM 判定
        kp_names_str = "\n".join([f"- {kp['id']}: {kp['name']}" for kp in kp_list])
        
        prompt = f"""請判斷學生的問題最符合下列哪一個知識點。
如果問題與任何知識點都沒有明確相關（例如閒聊、問時間、問天氣），請回答 "None"。
如果有多個相關，請選擇最核心的一個。

知識點清單:
{kp_names_str}

學生問題: "{query}"

請僅輸出對應的 知識點 ID 或 "None"。"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        ans = response.choices[0].message.content.strip()
        if ans.lower() == "none" or not ans.isdigit():
            return None
            
        detected_id = int(ans)
        # 驗證 ID 是否在清單中
        if any(kp["id"] == detected_id for kp in kp_list):
            return detected_id
            
        return None
    except Exception as e:
        print(f"Detect Knowledge Point Error: {e}")
        return None


def rerank_documents(
    documents: List[Dict], 
    weak_points: List[str], 
    top_k: int = 5,
    similarity_threshold: float = 0.3
) -> List[Dict]:
    """對搜尋結果進行重排序
    
    重排序邏輯：
    1. 過濾低於相似度門檻的結果
    2. 如果文件內容包含 weak_points 中的關鍵字，將其分數加權
    3. 按加權後分數降序排列
    
    Args:
        documents: 原始搜尋結果
        weak_points: 學生弱點知識點名稱列表
        top_k: 最終返回的文件數量
        similarity_threshold: 相似度門檻，低於此值會被過濾（預設 0.3）
        
    Returns:
        List[Dict]: 重排序後的文件列表，包含 original_score, rerank_score, boosted 欄位
    """
    
    # 沒有弱點時，直接過濾並返回
    if not weak_points:
        filtered = [doc for doc in documents if doc["similarity"] >= similarity_threshold]
        for d in filtered:
            d["original_score"] = d["similarity"]
            d["boosted"] = False
        return filtered[:top_k]
    
    reranked = []
    for doc in documents:
        score = doc["similarity"]
        
        # 過濾低相似度文件
        if score < similarity_threshold:
            continue
        
        content = doc.get("content") or ""
        
        # 計算加權倍數：每個匹配的弱點關鍵字加權 10%
        boost_multiplier = 1.0
        for wp in weak_points:
            if wp in content:
                boost_multiplier += 0.1
        
        # 上限控制：相似度最高為 1.0
        final_score = min(score * boost_multiplier, 1.0)
        
        new_doc = doc.copy()
        new_doc["original_score"] = score       # 保存原始分數
        new_doc["similarity"] = final_score     # 相容性：覆蓋原始值
        new_doc["rerank_score"] = final_score   # 明確的重排序分數
        new_doc["boosted"] = (boost_multiplier > 1.0)
        reranked.append(new_doc)
    
    # 按重排序分數降序排列
    reranked.sort(key=lambda x: x["similarity"], reverse=True)
    
    return reranked[:top_k]


# === Node 定義 ===

def retrieval_agent_node(state: StudentAgentState) -> Dict:
    """
    Retrieval Agent 節點
    
    職責：
    1. 根據使用者問題搜尋相關教材 chunks
    2. 根據學生弱點進行加權重排序
    3. 過濾低品質結果
    
    輸入（從 State 讀取）：
    - user_query: 使用者問題
    - weak_points: 弱點知識點列表（來自 Mastery Agent）
    
    輸出（更新 State）：
    - retrieved_chunks: 檢索到的教材片段（含完整內容）
    - chunk_sources: 來源資訊（含知識點名稱、單元名稱、頁碼等）
    """
    try:
        user_query = state["user_query"]
        weak_points = state.get("weak_points", [])
        course_id = state.get("course_id", 3) # 預設值需確認，應由 router 傳入
        
        # 步驟 1：生成查詢向量
        query_embedding = get_embedding(user_query)
        if not query_embedding:
            return {
                "retrieved_chunks": [],
                "chunk_sources": [],
                "error": create_error(
                    code="EMBEDDING_GENERATION_FAILED",
                    message="無法生成查詢的向量表示",
                    details={}
                )
            }
        
        # 步驟 2：向量搜尋 (Production Tables)
        # 先抓取 course 關聯的 contents，再搜 document_chunks
        candidates = search_documents(
            query_embedding, 
            course_id=course_id, 
            limit=20
        )
        
        # 步驟 3：重排序 + 過濾（最終取 3 筆）
        top_results = rerank_documents(
            candidates, 
            weak_points, 
            top_k=3,
            similarity_threshold=0.2
        )
        
        # 步驟 4：自動判定知識點 (Semantic Detection)
        detected_kp_id = detect_knowledge_point(user_query, course_id)
        
        # 步驟 5：格式化來源資訊（供前端來源卡片使用）
        sources = [
            {
                "chunk_id": doc["chunk_id"],
                "source_filename": doc.get("source_filename", "Unknown"),
                "page_numbers": doc.get("page_numbers", ""),
                "knowledge_point_name": doc.get("knowledge_point_name"),
                "unit_name": doc.get("unit_name"),
                "original_score": doc.get("original_score"),
                "rerank_score": doc.get("rerank_score", doc["similarity"]),
                "boosted": doc.get("boosted", False)
            }
            for doc in top_results
        ]
        
        return {
            "retrieved_chunks": top_results,
            "chunk_sources": sources,
            "rag_candidates_count": len(candidates),
            "detected_knowledge_point_id": detected_kp_id
        }
        
    except Exception as e:
        # 非致命錯誤：返回空結果但不中斷流程
        print(f"Retrieval Agent 發生錯誤: {e}")
        # 可以在此處加 log
        import traceback
        traceback.print_exc()
        return {
            "retrieved_chunks": [],
            "chunk_sources": []
        }
