"""
Knowledge Point Extractor Service

Extracts knowledge points from document summaries using LLM,
supporting hierarchical structure and relationship types.
"""

from typing import Dict, List, Optional
import json
from langchain_openai import ChatOpenAI
from backend.app.config.settings import settings
from backend.app.core.prompt_manager import PromptManager
from backend.app.utils import db_logger

# Initialize prompt manager
prompt_manager = PromptManager()


async def extract_knowledge_points(
    document_summary: str,
    file_name: str
) -> Dict:
    """
    從文件摘要中提取知識點
    
    Args:
        document_summary: 文件摘要文本
        file_name: 原始檔案名稱
        
    Returns:
        {
            "knowledge_points": [
                {
                    "mermaid_id": "A",
                    "name": "知識點名稱",
                    "level": "big_idea",
                    "description": "Can-do statement",
                    "confidence": 0.95,
                    "parent_mermaid_id": null
                }
            ],
            "relationships": [
                {
                    "from": "A",
                    "to": "B",
                    "type": "prerequisite"
                }
            ],
            "mermaid_graph": "graph TD\\n..."
        }
    """
    # Pre-flight: skip API call if document is clearly too short to have knowledge points
    MIN_SUMMARY_LENGTH = 30
    if len(document_summary.strip()) < MIN_SUMMARY_LENGTH:
        raise ValueError(
            f"文件內容太短（{len(document_summary.strip())} 字元），無法提取知識點。"
            "請確認所選文件包含學習內容。"
        )

    # Initialize LLM with API key from settings
    model_name = settings.agent.generator_model
    llm = ChatOpenAI(
        model=model_name,
        temperature=0.7,
        api_key=settings.openai_api_key
    )

    # Load prompts from YAML using dot-separated path
    system_prompt = prompt_manager.get_prompt("kp_extraction.system")
    user_prompt = prompt_manager.get_prompt(
        "kp_extraction.user",
        file_name=file_name,
        document_summary=document_summary
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    db_logger.logger.info(f"KP Extraction: Calling LLM for '{file_name}' (Summary: {len(document_summary)} chars)")

    response = await llm.ainvoke(messages)

    # Parse JSON output
    content = response.content

    # Strip markdown code block markers
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    # Guard: empty response
    if not content:
        raise ValueError("AI 未能從此文件提取知識點（回傳空內容），文件可能不含學習材料。")

    # Try direct JSON parse; if it fails, attempt to rescue a JSON block embedded in natural-language text
    import re as _re
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        db_logger.logger.warning(
            f"KP Extraction: Direct JSON parse failed for '{file_name}', attempting rescue..."
        )
        json_match = _re.search(r'\{.*\}', content, _re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                db_logger.logger.info("KP Extraction: JSON rescue succeeded.")
            except json.JSONDecodeError:
                db_logger.logger.error(
                    f"KP Extraction: JSON rescue also failed for '{file_name}'. Raw (first 200 chars): {content[:200]}"
                )
                raise ValueError("AI 回傳的格式無法解析，請稍後重試。")
        else:
            db_logger.logger.error(
                f"KP Extraction: No JSON found in LLM output for '{file_name}'. "
                f"Raw (first 200 chars): {content[:200]}"
            )
            raise ValueError("AI 未能從此文件提取知識點，請確認文件包含足夠的學習內容。")

    
    # 驗證並修正
    result = validate_and_fix_kp_extraction(result)
    
    db_logger.logger.info(f"KP Extraction: Successfully extracted {len(result['knowledge_points'])} KPs")
    
    # Extract usage metadata from LangChain response
    usage = {
        "prompt_tokens": response.usage_metadata.get('input_tokens', 0),
        "completion_tokens": response.usage_metadata.get('output_tokens', 0),
        "model_name": model_name
    }
    
    return {
        "kp_map": result,
        "usage": usage
    }


def validate_and_fix_kp_extraction(result: Dict) -> Dict:
    """
    驗證 LLM 輸出的完整性並修正常見錯誤
    
    Args:
        result: LLM 輸出的原始 JSON
        
    Returns:
        驗證並修正後的結果
    """
    # 檢查 1：至少要有 1 個 big_idea
    big_ideas = [kp for kp in result['knowledge_points'] if kp.get('level') == 'big_idea']
    if len(big_ideas) == 0:
        db_logger.logger.warning("KP Extraction: No big_idea found, upgrading top core_concept")
        core_concepts = [kp for kp in result['knowledge_points'] if kp.get('level') == 'core_concept']
        if core_concepts:
            top_concept = max(core_concepts, key=lambda x: x.get('confidence', 0))
            top_concept['level'] = 'big_idea'
    
    # 檢查 2：parent_mermaid_id 是否存在
    valid_ids = {kp['mermaid_id'] for kp in result['knowledge_points']}
    for kp in result['knowledge_points']:
        parent_id = kp.get('parent_mermaid_id')
        if parent_id and parent_id not in valid_ids:
            print(f"⚠️ 無效的 parent_id: {parent_id}，已移除")
            kp['parent_mermaid_id'] = None
    
    # 檢查 3：關係的 from/to 是否存在
    original_rel_count = len(result.get('relationships', []))
    result['relationships'] = [
        rel for rel in result.get('relationships', [])
        if rel.get('from') in valid_ids and rel.get('to') in valid_ids
    ]
    
    removed_count = original_rel_count - len(result['relationships'])
    if removed_count > 0:
        db_logger.logger.warning(f"KP Extraction: Removed {removed_count} invalid relationships")
    
    # 確保欄位存在
    if 'mermaid_graph' not in result:
        result['mermaid_graph'] = ""
    else:
        # Sanitize Mermaid graph
        graph = result['mermaid_graph']
        # Replace literal \n with actual newlines
        graph = graph.replace('\\n', '\n')
        # Ensure it starts with correct declaration if missing
        if not graph.strip().startswith('graph TD') and not graph.strip().startswith('graph LR'):
             # If it doesn't have a direction, maybe it's just the body
             if '-->' in graph or '--' in graph:
                 graph = 'graph TD\n' + graph
        
        # Remove any markdown code blocks if present inside the string (double protection)
        # Remove any markdown code blocks if present inside the string (double protection)
        graph = graph.replace('```mermaid', '').replace('```', '')
        
        # REGENERATE GRAPH FROM STRUCTURED DATA
        # This ensures 100% consistency with the GET endpoint and guarantees labels match relationships
        mermaid_lines = ["graph TD"]
        
        # Add nodes
        for kp in result.get('knowledge_points', []):
            safe_name = kp['name'].replace('"', "'").replace('[', '(').replace(']', ')')
            mermaid_lines.append(f"    {kp['mermaid_id']}[\"{safe_name}\"]")
            
        # Add relationships with bilingual label support
        for rel in result.get('relationships', []):
            from_id = rel['from']
            to_id = rel['to']
            rel_type = rel['type']
            rel_type_lower = str(rel_type).lower().strip()
            
            if rel_type_lower in ['prerequisite', '先備知識', '前置知識', '前置']:
                mermaid_lines.append(f"    {from_id} -->|先備知識| {to_id}")
            elif rel_type_lower in ['composition', '包含', '包含關係', '組成']:
                mermaid_lines.append(f"    {from_id} -->|包含| {to_id}")
            elif rel_type_lower in ['contrast', '對比', '比較', '對比概念']:
                mermaid_lines.append(f"    {from_id} -.比較.- {to_id}")
            elif rel_type_lower in ['extension', '延伸', '進階', '進階應用']:
                mermaid_lines.append(f"    {from_id} -.進階.-> {to_id}")
            else:
                mermaid_lines.append(f"    {from_id} --> {to_id}")
                
        result['mermaid_graph'] = "\n".join(mermaid_lines)
    
    return result


def extract_document_summary(pages: List[Dict]) -> str:
    """
    從文檔頁面中提取摘要
    
    策略：
    1. 前 10 頁完整內容（約 500 字/頁 = 5000 字）
    2. 所有章節/小節標題（結構化資訊）
    3. 若文檔過長，則每 5 頁抽樣一頁
    
    Args:
        pages: 文檔頁面列表，每頁包含 text 和 metadata
        
    Returns:
        文檔摘要字串（最多 8000 字元）
    """
    summary_parts = []
    
    # Part 1: 前 10 頁的完整內容
    for i, page in enumerate(pages[:10]):
        text = page.get('text', '')
        summary_parts.append(f"[Page {i+1}]\n{text[:500]}")
    
    # Part 2: 提取所有標題（若有結構化資訊）
    for page in pages:
        metadata = page.get('metadata', {})
        if 'headings' in metadata:
            summary_parts.extend(metadata['headings'])
    
    # Part 3: 若文檔很長（>20 頁），則每隔 5 頁抽樣一頁
    if len(pages) > 20:
        for i in range(10, len(pages), 5):
            text = pages[i].get('text', '')
            summary_parts.append(f"[Page {i+1} 摘要]\n{text[:300]}")
    
    full_summary = "\n\n".join(summary_parts)
    
    # 限制總長度在 8000 字以內
    return full_summary[:8000]
