"""
Scaffolding Agent Node

職責：
1. 整合上下文資訊（精熟度、RAG 檢索結果、對話歷史）
2. 使用 LLM 生成教學式回應
3. 提取引用來源並格式化為來源卡片

輸入（從 State 讀取）：
- user_query: 使用者問題
- current_mastery: 當前知識點精熟度
- weak_points: 弱點知識點列表
- retrieved_chunks: 檢索到的教材片段
- chunk_sources: 來源資訊
- condensed_history: 壓縮的對話歷史

輸出（更新 State）：
- scaffolding_strategy: 使用的教學策略
- final_response: LLM 生成的回應
- sources: 實際被引用的來源卡片資訊
"""

from typing import Dict, List, Optional, Union
import os
import re
from openai import OpenAI
from backend.app.agents.student_agent.state import StudentAgentState
from backend.app.agents.student_agent.nodes.start_node import create_error

# EcoLogits: 直接使用 llm_impacts 計算碳排（ContextVar 對獨立 client 無效）
import time as _time
try:
    from ecologits.tracers.utils import llm_impacts as _llm_impacts
    from ecologits import EcoLogits as _EcoLogits
    _ECOLOGITS_AVAILABLE = True
except Exception:
    _ECOLOGITS_AVAILABLE = False
# from backend.app.utils.db_logger import log_task # Removed

# === OpenAI 客戶端設定 ===
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=30.0,   # 回應生成需要較長時間
    max_retries=2
)

STUDENT_CHATBOT_MODEL = os.getenv("STUDENT_CHATBOT_MODEL", "gpt-4o-mini")

# === System Prompt ===

SYSTEM_PROMPT = """你是 Cook.ai 的 AI 學習助手，協助學生理解課程內容。

### 🎯 回應原則（核心）：

1. **依策略調整深度**（策略由系統根據精熟度與對話輪次自動決定）：
   - `Direct Explanation`：完整解釋，可附進階思考題。
   - `Balanced`：先給核心答案，再可選附一個引導問題。
   - `Guided Questioning`：**不要直接回答問題**。根據學生的問題，給出思考方向或提示，
     引導學生先嘗試自己思考。語氣要鼓勵，讓學生有信心嘗試回答。
     **切記：此策略下絕對不要給出完整答案。**
     回應必須以一個**引導問題**作為唯一結尾，並符合以下格式：
     - 前面提示文字結束後，必須空一行。
     - 引導問題必須用 Markdown 粗體（用 ** 包裹）。
     - **注意：嚴禁在同一則回應中重複出現一模一樣的句子，確保該引導問題僅在結尾出現一次，不要在正文中提前洩露。**
   - `Scaffolded Answer`：這是學生回應引導問題後的第二輪對話。
     先針對學生的回答給予回饋（肯定正確的部分、修正錯誤的部分），
     然後提供完整的解答。可附上進階延伸問題（可選）。

2. **每則回應最多只問一個問題**，不要連續列出多個問題轟炸學生。

3. **鼓勵學生**：即使學生答錯，也要肯定其思考過程，再引導修正。

4. **避免冗餘**：嚴禁在同一則回應中重複顯示相同的內容或句子，特別是結尾處的提示與引導問題。

### 📚 上下文利用：
- 優先使用【參考教材】的內容回答問題。
- 使用了【參考教材】中的資訊時，**必須在相關句尾標註來源 ID**，例如 `[doc:123]`。
- **只能引用【參考教材】清單中實際存在的 [doc:ID]，嚴禁捏造或引用不存在的 ID。**

### 📝 回應格式：
- 語氣友善且專業，直接輸出回應，不要說「我來」、「接下來我將」等序言。
- 使用 Markdown 格式：標題、條列、表格（若學生要求表格就直接給表格）。
"""


def construct_prompt(state: StudentAgentState) -> str:
    """建構給 LLM 的完整 User Prompt
    
    組裝順序：
    1. 精熟度資訊
    2. 對話歷史
    3. RAG 檢索到的參考教材
    4. 使用者問題
    """
    # 1. 使用者問題
    query = state["user_query"]
    
    # 2. 精熟度上下文
    current_mastery = state.get("current_mastery", [])
    
    if isinstance(current_mastery, list) and current_mastery:
        # 新格式：單元內所有 KP 精熟度列表
        mastery_info = "《學生狀態 — 單元知識點精熟度》\n"
        for m in current_mastery:
            level = m.get("mastery_level") or "尚無記錄"
            name = m.get("knowledge_point_name", "?")
            mastery_info += f"- {name}: {level}\n"
    else:
        mastery_info = "《學生狀態》: 尚無精熟度記錄（學生可能尚未預習此單元）"
    
    weak_points = state.get("weak_points", [])
    if weak_points:
        mastery_info += f"\n弱點知識點: {', '.join(weak_points)}"
    
    # 3. RAG 檢索結果
    rag_text = ""
    chunks = state.get("retrieved_chunks", [])
    if chunks:
        rag_text = "【參考教材】:\n"
        for chunk in chunks:
            content = chunk.get("content", "")
            chunk_id = chunk.get("chunk_id", "unknown")
            source_filename = chunk.get("source_filename", "unknown")
            page_numbers = chunk.get("page_numbers", "")
            # 格式：[doc:ID] (檔名 p.頁碼) 內容
            rag_text += f"- [doc:{chunk_id}] ({source_filename} p.{page_numbers}) {content}\n"
    else:
        rag_text = "【參考教材】: 無相關教材。"
    
    # 4. 對話歷史
    history = state.get("condensed_history", "")
    if history:
        history_text = f"【最近對話】:\n{history}"
    else:
        history_text = "【最近對話】: 無"
    
    # 5. 跨對話相關歷史（迷思概念偵測，只含學生提問，已壓縮）
    related_dialogs = state.get("related_dialogs", [])
    if related_dialogs:
        related_text = "【跨對話相關歷史】（學生在其他對話中問過的類似問題，可能反映反覆出現的迷思概念）:\n"
        for rd in related_dialogs[:3]:
            content = rd.get("content", {})
            msg = content.get("message", str(content)) if isinstance(content, dict) else str(content)
            related_text += f"- {msg}\n"
    else:
        related_text = ""
    
    # 組裝完整 Prompt
    full_prompt = f"""
{mastery_info}

{history_text}

{related_text}

{rag_text}

---
學生問題: {query}

請根據以上資訊與教學策略指引，生成回應。
"""
    return full_prompt


def identify_strategy(current_mastery: Union[List[Dict], Dict], weak_points: List[str], recent_dialogs: List[Dict]) -> str:
    """根據精熟度與對話輪次決定教學策略（規則式）
    
    - 第一輪（recent_dialogs < 2）：待加強/尚可 → Guided Questioning（只引導不給答案）
    - 第二輪起（recent_dialogs >= 2）：待加強/尚可 → Scaffolded Answer（回饋+完整解答）
    - 精熟 → 直接回答（不受輪次影響）
    - unknown → Balanced
    """
    # 取所有 KP 中最差的精熟度作為主要判斷依據
    level = ""
    if isinstance(current_mastery, list) and current_mastery:
        # 優先級: 待加強 > 尚可 > 精熟
        levels = [m.get("mastery_level", "") for m in current_mastery if m.get("mastery_level")]
        if any("待加強" in l or "Needs Improvement" in l for l in levels):
            level = "待加強"
        elif any("尚可" in l or "Passable" in l for l in levels):
            level = "尚可"
        elif levels:
            level = levels[0]
    elif isinstance(current_mastery, dict):
        # 向後相容：舊 dict 格式
        level = current_mastery.get("mastery_level", "")
    
    # 判斷對話輪次：每一輪 = 1 user + 1 assistant = 2 entries
    is_first_round = len(recent_dialogs) < 2

    # 1. 精熟 → 直接回答（不受輪次影響）
    if "精熟" in level or "Proficient" in level:
        return "Direct Explanation"
    
    # 2. 待加強 / 尚可 / 有弱點 → 依輪次切換策略
    if "待加強" in level or "Needs Improvement" in level or "尚可" in level or "Passable" in level or weak_points:
        if is_first_round:
            return "Guided Questioning"
        else:
            return "Scaffolded Answer"
    
    # 3. 預設（unknown 或無記錄）→ Balanced
    return "Balanced"


# === Node 定義 ===

def scaffolding_agent_node(state: StudentAgentState) -> Dict:
    """
    Scaffolding Agent 節點
    
    職責：
    1. 整合上下文資訊（精熟度、RAG 結果、對話歷史）
    2. 呼叫 LLM 生成教學式回應
    3. 提取實際引用的來源並格式化為來源卡片
    
    輸入（從 State 讀取）：
    - user_query: 使用者問題
    - current_mastery: 當前知識點精熟度
    - weak_points: 弱點知識點列表
    - retrieved_chunks: 檢索到的教材片段
    - chunk_sources: 來源資訊
    
    輸出（更新 State）：
    - scaffolding_strategy: 使用的教學策略
    - final_response: LLM 生成的回應
    - sources: 實際被引用的來源卡片（含 title, section, snippet, locator）
    """
    try:
        user_query = state["user_query"]
        
        # 驗證輸入
        if not user_query:
            return {
                "error": create_error(
                    code="EMPTY_USER_QUERY",
                    message="使用者問題為空",
                    details={}
                )
            }
        
        # 步驟 1：決定教學策略（規則式預判）
        strategy = identify_strategy(
            state.get("current_mastery", {}), 
            state.get("weak_points", []),
            state.get("recent_dialogs", [])
        )
        
        # 步驟 2：建構 Prompt
        user_prompt = construct_prompt(state)
        
        # 強制將策略加入 Prompt，確保 LLM 遵循（特別是當對話過長時的策略調整）
        user_prompt += f"\n\n【當前教學策略】: {strategy}\n若策略為 'Balanced' 或 'Direct'，請減少反問，適度給予直接解釋或提示，避免無限迴圈。"
        
        # 步驟 3：呼叫 LLM 生成回應
        _timer_start = _time.perf_counter()
        response = openai_client.chat.completions.create(
            model=STUDENT_CHATBOT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.15  # 降低 temperature 提升引用格式穩定性
        )
        _request_latency = _time.perf_counter() - _timer_start
        
        final_text = response.choices[0].message.content
        usage = response.usage
        _model_name = STUDENT_CHATBOT_MODEL
        
        # 步驟 3b：直接計算 EcoLogits 環境影響（不依賴 ContextVar）
        env_impact = None
        if _ECOLOGITS_AVAILABLE and usage:
            try:
                impacts = _llm_impacts(
                    provider="openai",
                    model_name=getattr(response, 'model', 'gpt-4o-mini'),
                    output_token_count=usage.completion_tokens or 0,
                    request_latency=_request_latency,
                    electricity_mix_zone=_EcoLogits.config.electricity_mix_zone
                )
                if impacts is not None:
                    env_impact = {
                        "carbon_g": impacts.gwp.value.mean * 1000,
                        "energy_kwh": impacts.energy.value.mean,
                        "water_l": impacts.wcf.value.mean,
                        "adpe_kgseb": impacts.adpe.value.mean,
                        "pe_mj": impacts.pe.value.mean
                    }
            except Exception:
                pass  # EcoLogits 計算失敗不影響主流程
        
        # 步驟 4：提取實際引用的來源
        # 使用 regex 從回應中提取 doc ID（支援全形和半形括號）
        chunk_sources = state.get("chunk_sources", [])
        used_ids = set(re.findall(r"[【\[]doc:(\d+)[】\]]", final_text or ""))
        
        # 建立內容查找表以生成 snippet
        chunk_content_map = {
            str(c.get("chunk_id")): c.get("content", "") 
            for c in state.get("retrieved_chunks", [])
        }
        
        # 步驟 5：組裝豐富的來源卡片資訊
        sources = []
        for s in chunk_sources:
            c_id = str(s.get("chunk_id"))
            if c_id in used_ids:
                content = chunk_content_map.get(c_id, "")
                snippet = content[:100] + "..." if len(content) > 100 else content
                
                sources.append({
                    "chunk_id": s["chunk_id"],
                    "title": s.get("knowledge_point_name", "未知知識點"),
                    "section": s.get("unit_name", "未知單元"),
                    "snippet": snippet,
                    "page_numbers": s.get("page_numbers", ""),
                    "source_filename": s.get("source_filename", ""),
                    "locator": f"{s.get('unit_name', '')} | 頁碼 {s.get('page_numbers', '')}"
                })
        
        # Plan B Fallback：若 LLM 沒有引用任何 [doc:ID]，顯示所有 RAG 檢索到的來源
        if not sources and chunk_sources:
            for s in chunk_sources:
                c_id = str(s.get("chunk_id"))
                content = chunk_content_map.get(c_id, "")
                snippet = content[:100] + "..." if len(content) > 100 else content
                sources.append({
                    "chunk_id": s["chunk_id"],
                    "title": s.get("knowledge_point_name") or s.get("source_filename", "參考資料"),
                    "section": s.get("unit_name", "未知單元"),
                    "snippet": snippet,
                    "page_numbers": s.get("page_numbers", ""),
                    "source_filename": s.get("source_filename", ""),
                    "locator": f"{s.get('unit_name', '')} | 頁碼 {s.get('page_numbers', '')}"
                })
        
        # 步驟 7：整合 Usage (從 State 取得累積值並加入本次)
        prev_usage = state.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        current_usage = {
            "prompt_tokens": prev_usage.get("prompt_tokens", 0) + usage.prompt_tokens,
            "completion_tokens": prev_usage.get("completion_tokens", 0) + usage.completion_tokens,
            "total_tokens": prev_usage.get("total_tokens", 0) + usage.total_tokens
        }

        return {
            "scaffolding_strategy": strategy,
            "final_response": final_text,
            "sources": sources,
            "usage": current_usage,
            "full_prompt": user_prompt,
            "environmental_impact": env_impact,
            "model_name": _model_name,
        }
        
    except Exception as e:
        # 錯誤時返回 fallback 回應並保留舊的 usage
        print(f"Scaffolding Agent 發生錯誤: {e}")
        return {
            "scaffolding_strategy": "error_fallback",
            "final_response": "抱歉，我目前無法處理您的請求，請稍後再試。",
            "sources": [],
            "usage": state.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            "error": create_error(
                code="SCAFFOLDING_ERROR",
                message="回應生成失敗",
                details={"exception": str(e)}
            )
        }
