import os
import json
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field, field_validator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.teacher_agent.rag_agent import rag_agent
from backend.app.utils import db_logger
from backend.app.utils.db_logger import log_task, log_task_sources
from backend.app.agents.teacher_agent.utils.llm_utils import MODEL_PRICING, get_llm, _prepare_multimodal_content
from backend.app.core.prompt_manager import prompt_manager

import logging
logger = logging.getLogger(__name__)

from .state import SummarizationState

# --- Pydantic Models for Structured Summary Output ---
class SummarySection(BaseModel):
    section_title: str = Field(..., description="The title of the summary section.")
    related_kps: Optional[List[str]] = Field(
        default=None, 
        description="List of knowledge point names covered by this section. Leave null or empty if this section (e.g. intro or summary) does not map to a specific KP."
    )
    content_list: List[str] = Field(
        ..., 
        description="A list of content strings. IMPORTANT: The first item should be a descriptive paragraph (no prefix). Remaining items MUST start with '- ' or '1. ' to ensure proper list formatting in the UI."
    )
    chunk_ids: Optional[List[int]] = Field(default=None, description="IDs of attributed chunks (injected by vector search).")
    match_scores: Optional[List[int]] = Field(default=None, description="Match scores for each chunk (0-100).")

    @field_validator('related_kps', mode='before')
    @classmethod
    def filter_none_kps(cls, v):
        """Remove None/null items that the LLM may inject inside the list, or wrap single string in list."""
        if v is None:
            return None
        if isinstance(v, str):
            # If accidentally passed as string (common error), wrap it in list
            return [v]
        if isinstance(v, list):
            cleaned = [item for item in v if item is not None]
            return cleaned if cleaned else None
        return v

class SummaryReport(BaseModel):
    title: str = Field(..., description="The main title of the summary report.")
    sections: List[SummarySection] = Field(
        ..., 
        description="A list of sections. Organize flexibly based on pedagogical needs: merge related KPs or split large KPs."
    )

# --- Node Functions ---

@log_task(
    agent_name="retriever", 
    input_extractor=lambda state: {
        "query": state.get("query"), 
        "source_ids": state.get("source_ids"),
        "selected_kp_names": state.get("selected_kp_names"),
        "generated_source_ids": state.get("generated_source_ids"),
        "unit_id": state.get("unit_id"),
        "length": state.get("length"), # Log length to track dynamic top_k
        "ablation_group": state.get("ablation_group")
    }
)
def retrieve_chunks_node(state: SummarizationState) -> dict:
    """
    Retrieves context using RAGAgent and populates the state.
    """
    try:
        # Determine top_k based on mode: reverted to 10 based on user feedback to prevent context bleed
        top_k = 10
        
        rag_results = rag_agent.search(
            user_prompt=state["query"], 
            unique_content_ids=state["source_ids"],
            top_k=top_k, 
            selected_kp_names=state.get("selected_kp_names"),
            generated_course_content_ids=state.get("generated_source_ids", []),
            unit_id=state.get("unit_id"),
            ablation_group=state.get("ablation_group")
        )
        
        enriched_chunks = rag_results["text_chunks"]
        enriched_pages = rag_results["page_content"]

        
        # The decorator has already created the task and injected its ID into the state
        log_task_sources(state["current_task_id"], enriched_chunks)

        return {
            "retrieved_page_content": enriched_pages,
            "retrieved_text_chunks": enriched_chunks,
            "rag_metrics": rag_results.get("rag_metrics", {}), # For task output log
            "parent_task_id": state["current_task_id"] # Set self as parent for the next node
        }
    except Exception as e:
        return {"error": f"Failed to retrieve context: {str(e)}"}

@log_task(
    agent_name="summarizer",
    input_extractor=lambda state: {
        "query": state.get("query"),
        "unit_name": state.get("unit_name"),
        "source_ids": state.get("source_ids"),
        "material_type": state.get("material_type"),
        "length": state.get("length"),
        "selected_kp_names": state.get("selected_kp_names"),
        "critic_suggestions": state.get("critic_feedback", [])[-1].get("suggestions") if state.get("critic_feedback") else None
    }

)
def summarize_node(state: SummarizationState) -> dict:
    """
    Generates a structured summary and attributes chunks via vector search.
    """
    try:
        # 0. Check if previous node (retriever) failed
        if state.get("error"):
            raise ValueError(f"Retriever failed with error: {state['error']}")

        # 1. Prepare multimodal content (Separated by category)
        retrieved_page_content = state.get("retrieved_page_content")
        if not retrieved_page_content:
            raise ValueError("No content found in state for summarization.")

        # Separate original docs vs existing materials
        original_pages = [p for p in retrieved_page_content if p.get("source_category") == "original_document"]
        existing_pages = [p for p in retrieved_page_content if p.get("source_category") == "existing_material"]
        
        # If rag_agent didn't have category yet (fallback), treat all as original
        if not original_pages and not existing_pages:
            original_pages = retrieved_page_content

        combined_text_new, image_data_urls = _prepare_multimodal_content(original_pages)
        combined_text_existing, _ = _prepare_multimodal_content(existing_pages)
        
        # 🔍 DEBUG: Log existing material text for redundancy check verification
        if combined_text_existing:
            logger.info(f"📚 Existing material text retrieved ({len(combined_text_existing)} chars):")
            # Log first 500 chars to avoid overwhelming logs but give enough context
            logger.info(f"--- START EXISTING MATERIAL ---\n{combined_text_existing[:500]}...\n--- END EXISTING MATERIAL ---")
        else:
            logger.info("📚 No existing material text found for this request.")
        
        if not combined_text_new and not image_data_urls and not combined_text_existing:
            raise ValueError("No text or images extracted from the document.")

        # 2. Prepare KP structure with Boundary Context
        selected_kp_names = state.get("selected_kp_names") or []
        unit_id = state.get("unit_id")
        other_kp_names = []
        
        if unit_id:
            from sqlalchemy import text
            from backend.app.db import engine
            try:
                with engine.connect() as conn:
                    query = text("SELECT name FROM knowledge_points WHERE unit_id = :uid")
                    result = conn.execute(query, {"uid": unit_id}).fetchall()
                    all_kps = [r[0] for r in result]
                    other_kp_names = [name for name in all_kps if name not in selected_kp_names]
            except Exception as e:
                logger.error(f"❌ Failed to fetch unit KPs: {e}")

        # 🔍 DEBUG: Log KP boundary context
        logger.info(f"📍 Selected KPs: {selected_kp_names}")
        if other_kp_names:
            logger.info(f"🚫 Other KPs (Boundary): {other_kp_names}")
        else:
            logger.info("ℹ️ No other KPs found for this unit (no boundary context needed).")

        kp_structure = _format_kp_structure(selected_kp_names, other_kp_names)
        
        # 3. Select prompt based on material_type and get length mode
        material_type = state.get("material_type", "preview")
        length = state.get("length", "standard")  # Get length mode: concise, standard, detailed
        
        # 🔍 DEBUG: Log the parameters being used
        logger.info(f"📏 Summary Generation - material_type: {material_type}, length: {length}")
        logger.info(f"🔑 Attempting to get prompt: summarization.{'preview' if material_type == 'preview' else 'review'}_user")
        
        if material_type == "preview":
            system_prompt = prompt_manager.get_prompt("summarization.preview_system")
            user_prompt = prompt_manager.get_prompt(
                "summarization.preview_user",
                combined_text=combined_text_new,
                existing_material_text=combined_text_existing,
                kp_structure=kp_structure,
                length=length,
                unit_name=state.get("unit_name"),
                user_query=state.get("query", "（無額外要求）")
            )

        else:  # review
            system_prompt = prompt_manager.get_prompt("summarization.review_system")
            user_prompt = prompt_manager.get_prompt(
                "summarization.review_user",
                combined_text=combined_text_new,
                existing_material_text=combined_text_existing,
                kp_structure=kp_structure,
                length=length,
                unit_name=state.get("unit_name"),
                user_query=state.get("query", "（無額外要求）")
            )

        
        # 4. Handle refinement if feedback exists
        critic_feedback = state.get("critic_feedback", [])
        if critic_feedback:
            latest_feedback = critic_feedback[-1]
            previous_content = state.get("final_generated_content", {})
            
            # Format refinement instruction
            refinement_instruction = "\n\n" + "="*20 + " 重點改進指示 " + "="*20 + "\n"
            refinement_instruction += "你在上一次生成中收到了以下 Critic 評估建議，請在此次生成中優先解決這些問題：\n\n"
            
            # Extract suggestions (could be from our new format)
            suggestions = latest_feedback.get("suggestions", [])
            if not suggestions and "feedback_items" in latest_feedback:
                # Fallback to extracting from feedback_items if standard suggestions field is empty
                suggestions = latest_feedback["feedback_items"].get("all_suggestions", [])
            
            if suggestions:
                for idx, s in enumerate(suggestions, 1):
                    refinement_instruction += f"{idx}. {s}\n"
            else:
                refinement_instruction += "(未提供具體建議，請全面檢查內容品質)\n"
            
            refinement_instruction += "\n**上一次生成的內容（供參考）：**\n"
            refinement_instruction += json.dumps(previous_content, ensure_ascii=False, indent=2)
            refinement_instruction += "\n" + "="*50 + "\n"
            
            user_prompt += refinement_instruction

        # 5. Construct multimodal messages
        human_message_content = [{"type": "text", "text": user_prompt}]
        if image_data_urls:
            for image_uri in image_data_urls:
                human_message_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_uri, "detail": "low"}
                })

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message_content)
        ]

        # 5. Call LLM with Tool Calling
        llm = get_llm(model_name=state.get("model_name"))
        summarizer_llm = llm.bind_tools(
            tools=[SummaryReport], 
            tool_choice={"type": "function", "function": {"name": "SummaryReport"}}
        )
        response = summarizer_llm.invoke(messages)
        
        if not response.tool_calls:
            raise ValueError("The summarizer model did not call the required 'SummaryReport' tool.")
            
        summary_report = SummaryReport(**response.tool_calls[0]['args'])
        
        # 6. Vector search attribution
        from backend.app.agents.teacher_agent.utils.summary_citation_validator import SummaryCitationValidator
        
        validator = SummaryCitationValidator(state["retrieved_text_chunks"])
        summary_report_dict = summary_report.model_dump()
        
        summary_report_dict["sections"] = validator.attribute_summary_sections(
            summary_report_dict["sections"], 
            top_k=3, min_score=0.40
        )
        
        # 7. Extract token usage and cost
        token_usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        model_name = llm.model_name
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        # 8. Return final content
        return {
            "final_generated_content": {
                "type": "summary",
                "subtype": material_type,  # 'preview' or 'review'
                **summary_report_dict
            },
            "retrieved_text_chunks": state.get("retrieved_text_chunks"),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name,
            "parent_task_id": state.get("current_task_id")
        }

    except Exception as e:
        error_message = f"Failed to generate structured summary: {str(e)}"
        return {
            "error": error_message,
            "final_generated_content": None
        }


def _format_kp_structure(selected_kps: List[str], other_kps: List[str] = None) -> str:
    """Format KP structure for LLM reference with boundary context"""
    if not selected_kps:
        return "（教師未指定特定知識點，請根據教材內容自行組織結構）"
    
    kp_structure = "**--- [連貫導讀與建議] 本次生成目標知識點 ---**\n"
    kp_structure += "以下知識點是本次生成的教學核心。請針對以下點進行「深度解構」與「展開」：\n"
    for idx, kp in enumerate(selected_kps, 1):
        kp_structure += f"- {kp}\n"
    
    if other_kps:
        kp_structure += "\n**--- [連貫性與背景導讀建議] 單元內其他知識點 ---**\n"
        kp_structure += "以下知識點屬於本單元的其他部分。你可以在背景知識中「輕微提及」，但請不要以下內容進行細節展開或建立獨立 Section：\n"
        for kp in other_kps:
            kp_structure += f"- {kp} (請忽視詳細細節)\n"
    
    return kp_structure
