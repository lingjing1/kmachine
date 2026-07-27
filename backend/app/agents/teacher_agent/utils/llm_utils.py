from typing import List, Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.app.config.settings import settings
from backend.app.core.prompt_manager import prompt_manager
from backend.app.utils import db_logger

# --- Pricing Info ---
# DEPRECATED: Use db_logger.calculate_llm_cost instead.
# Keeping it for backward compatibility if needed by other components temporarily.
MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
}

ALLOWED_MODELS = {
    "gpt-4o-mini": "GPT-4o Mini (快速, 低成本)",
    "gpt-4o": "GPT-4o (均衡, 推薦)",
    "o4-mini": "o4-mini (深度推理)"
}

def get_llm(model_name: str = None) -> ChatOpenAI:
    """Initializes the ChatOpenAI model. Accepts an optional per-request model override."""
    name = model_name if model_name and model_name in ALLOWED_MODELS else settings.agent.generator_model
    # timeout: 單次 LLM 呼叫的總上限(送出到整段回應收完),避免 OpenAI 卡住時長時間佔住執行緒。
    #          注意這是「每次呼叫」的上限,不是整個生成任務的上限;一筆任務通常會呼叫多次。
    # max_retries: 暫時性錯誤(429/5xx)自動重試,維持 langchain 預設值並明示意圖。
    return ChatOpenAI(model=name, timeout=120, max_retries=2)

def call_openai_api(llm: ChatOpenAI, prompt: str, images: List[str] = None) -> Any:
    """Calls the LLM with a multimodal payload and returns the full response object."""
    message_content = [{"type": "text", "text": prompt}]
    if images:
        for image_uri in images:
            message_content.append({
                "type": "image_url",
                "image_url": {"url": image_uri, "detail": "low"}
            })
    
    system_prompt = prompt_manager.get_prompt("system.common.educational_expert")
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message_content)
    ]
    response = llm.invoke(messages)
    return response

def _prepare_multimodal_content(retrieved_page_content: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """Prepares content from structured page content for the LLM."""
    max_images = settings.agent.max_images_per_prompt
    combined_text_parts, image_data_urls, image_source_map = [], [], []

    if not retrieved_page_content:
        return "", []

    for item in retrieved_page_content:
        if item.get("type") == "structured_page_content":
            page_num = item.get("page_number", "Unknown")
            doc_name = item.get("document_name", "Unknown Document")
            combined_text_parts.append(f"\n\n--- [START] Source: {doc_name} (Page {page_num}) ---")
            page_content = item.get("content", [])
            for element in page_content:
                if element.get("type") == "text":
                    combined_text_parts.append(element.get("content", ""))
                elif element.get("type") == "image" and len(image_data_urls) < max_images:
                    base64_data = element.get("base64")
                    if base64_data:
                        mime_type = element.get("mime_type", "image/jpeg")
                        valid_image_url = f"data:{mime_type};base64,{base64_data}" if not base64_data.startswith("data:") else base64_data
                        image_data_urls.append(valid_image_url)
                        image_index = len(image_data_urls)
                        combined_text_parts.append(f"\n[Image {image_index} is here. Source: Page {page_num}]\n")
                        image_source_map.append(f"Image {image_index}: Sourced from Page {page_num}")
            combined_text_parts.append(f"--- [END] Source: Page {page_num} ---\n")

    final_text = "\n".join(combined_text_parts)
    if image_source_map:
        final_text += "\n\n--- Image Source Key ---\n" + "\n".join(image_source_map)
    return final_text, image_data_urls
