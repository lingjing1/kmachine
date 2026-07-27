import time
import json
import logging
from typing import Literal, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from backend.app.utils.time_utils import get_now_taipei
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

from .state import TeacherAgentState
from backend.app.utils import db_logger
from backend.app.utils.db_logger import log_task
from backend.app.agents.teacher_agent.utils.llm_utils import get_llm, MODEL_PRICING
from backend.app.agents.teacher_agent.skills.exam_generator.graph import app as exam_generator_app
from backend.app.agents.teacher_agent.skills.general_chat.nodes import general_chat_node
from backend.app.agents.teacher_agent.skills.summarization.graph import app as summarization_app # New import
from backend.app.agents.teacher_agent.skills.base import SKILL_CONFIGS  # Skill configuration system
# TEMPORARILY DISABLED FOR TESTING - Critic integration
# from backend.app.agents.teacher_agent.critics.graph import critic_app # Import Critic Agent
# from backend.app.agents.teacher_agent.critics.state import CriticState # Import Critic State

# --- Pydantic Model for the Router's Tool ---
class Route(BaseModel):
    """Select the next skill to use based on the user's query."""
    next_skill: Literal["exam_generation_skill", "general_chat_skill", "summarization_skill"] = Field(..., description="The name of the skill to use next.") # Updated Literal

# --- Router Node ---

@log_task(agent_name="teacher_agent_router", input_extractor=lambda state: {"user_query": state.get("user_query")})
def router_node(state: TeacherAgentState) -> dict:
    """
    Determines which skill to use based on the user's query using an LLM.
    If next_node is already set (e.g., in manual refinement), it bypasses LLM logic.
    """
    # Bypassing for manual refinement or specific triggers
    if state.get("next_node"):
        logger.info(f"Bypassing router: next_node '{state['next_node']}' already set.")
        return {
            "next_node": state["next_node"],
            "action_taken": f"Bypassed router to {state['next_node']}.",
            "parent_task_id": state.get("current_task_id")
        }
    
    user_query = state.get("user_query", "")
    
    system_prompt = (
        "You are an expert router agent. Your job is to analyze the user's query and "
        "decide which of the available skills is most appropriate to handle the request. "
        "You must call the `Route` tool to indicate your decision."
    )
    
    skill_descriptions = [
        "## Available Skills:",
        "1. `exam_generation_skill`: Use this skill when the user explicitly asks to create, generate, or make an exam, test, quiz, or questions (e.g., '幫我出5題選擇題', 'generate a test', '生成測驗', '出題目').",
        "2. `summarization_skill`: Use this skill when the user asks to summarize, create an overview, or get the key points of the course material (e.g., '幫我總結這份教材', '給我這份文件的重點', '生成預習教材', '摘要整理', 'summarize this doc').", # New skill description
        "3. `general_chat_skill`: Use this as a fallback for any other query. This includes greetings, general questions, or requests that do not involve generating an exam or summary (e.g., '你好', '你是誰?', 'What can you do?')."
    ]
    
    human_prompt = "\n".join(skill_descriptions) + f"\n\n**User Query:**\n\"{user_query}\""
    
    try:
        llm = get_llm()
        router_llm = llm.bind_tools(tools=[Route], tool_choice="Route")
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        
        response = router_llm.invoke(messages)
        
        if not response.tool_calls:
            raise ValueError("The router model did not call the required 'Route' tool.")
        
        chosen_route = Route(**response.tool_calls[0]['args'])
        next_node = chosen_route.next_skill
        
        logger.info(f"LLM Router decided: {next_node}")

        token_usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        model_name = llm.model_name
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        return {
            "next_node": next_node,
            "action_taken": f"Routed to {next_node} skill.",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name,  # Add model_name
            "parent_task_id": state.get("current_task_id")  # Propagate parent_task_id for skill nodes
        }

    except Exception as e:
        # Fallback to keyword routing if LLM router fails
        logger.warning(f"LLM router failed: {e}. Falling back to keyword routing.")
        exam_keywords = ["exam", "test", "quiz", "考卷", "測驗", "題目"]
        summarize_keywords = ["summarize", "summary", "overview", "總結", "重點", "概述"] # New keywords for fallback
        
        if any(keyword in user_query.lower() for keyword in exam_keywords):
            next_node = "exam_generation_skill"
        elif any(keyword in user_query.lower() for keyword in summarize_keywords): # New fallback condition
            next_node = "summarization_skill"
        else:
            next_node = "general_chat_skill"
        return {
            "next_node": next_node,
            "action_taken": f"LLM router failed, falling back to keyword routing. Routed to {next_node} skill.",
            # "error": f"LLM router failed: {e}", # Do not set error, as we recovered via fallback
            "parent_task_id": state.get("current_task_id")  # Propagate parent_task_id even in error case
        }


# --- Conditional Edge Function ---

def should_continue(state: TeacherAgentState) -> str:
    """
    Determines the next node to visit based on the router's decision.
    """
    return state.get("next_node")

# --- Skill Nodes ---

def exam_skill_node(state: TeacherAgentState) -> dict:
    """
    Executes the exam generation sub-graph.
    The logging is handled by the @log_task decorator.
    """
    try:
        # Use the iteration count from state (already correctly set by router/orchestrator or loop logic)
        current_iteration = state.get("iteration_count", 1)
        
        # The decorator injects the current task's ID into the state.
        # We use it as the parent_task_id for the sub-graph we are about to call.
        skill_input = {
            "job_id": state["job_id"],
            "query": state.get("query", state["user_query"]),
            "source_ids": state.get("source_ids", []),
            "generated_source_ids": state.get("generated_source_ids", []),
            "selected_kp_names": state.get("selected_kp_names", []),
            "unit_name": state.get("unit_name"),
            "unit_id": state.get("unit_id"),
            
            # Explicit parameters from UI
            "question_types": state.get("question_types", []),
            "question_count": state.get("question_count", 0),
            "ablation_group": state.get("ablation_group"),

            "parent_task_id": state.get("current_task_id"), # Parent is the router/orchestrator node
            "iteration_count": current_iteration,
            "critic_feedback": state.get("critic_feedback", []),
            "final_generated_content": state.get("final_generated_content")
        }
        final_skill_state = exam_generator_app.invoke(skill_input)

        if final_skill_state.get("error"):
            raise Exception(f"Exam generator skill failed: {final_skill_state['error']}")
        final_result = final_skill_state
        generated_content = final_skill_state.get("final_generated_content")
        
        # Return minimal metadata for orchestrator output (not the full result)
        return {
            "final_result": final_result,  # Keep for state propagation
            "final_generated_content": generated_content,
            "retrieved_text_chunks": final_skill_state.get("retrieved_text_chunks", []),  # ✅ 傳遞 RAG 資料
            "parent_task_id": state.get("current_task_id"),
            "iteration_count": current_iteration,  # Use current_iteration
            # Metadata for database output (minimal)
            "_router_output": {
                "status": "success",
                "content_generated": bool(generated_content),
                "iteration": current_iteration  # Log current iteration
            }
        }

    except Exception as e:
        return {"error": str(e)}

def summarization_skill_node(state: TeacherAgentState) -> dict: # New skill node
    """
    Executes the summarization sub-graph.
    The logging is handled by the @log_task decorator.
    """
    try:
        # Use the iteration count from state
        current_iteration = state.get("iteration_count", 1)
        
        skill_input = {
            "job_id": state["job_id"],
            "query": state.get("query", state["user_query"]),
            "source_ids": state.get("source_ids", []),
            "generated_source_ids": state.get("generated_source_ids", []),
            "selected_kp_names": state.get("selected_kp_names", []),
            "unit_name": state.get("unit_name"),
            "unit_id": state.get("unit_id"),

            "material_type": state.get("material_type", "preview"),
            "length": state.get("length", "standard"),
            "ablation_group": state.get("ablation_group"),
            "parent_task_id": state.get("current_task_id"),
            "iteration_count": current_iteration,
            "critic_feedback": state.get("critic_feedback", []),
            "final_generated_content": state.get("final_generated_content")
        }
        final_skill_state = summarization_app.invoke(skill_input)

        if final_skill_state.get("error"):
            raise Exception(f"Summarization skill failed: {final_skill_state['error']}")
        
        final_result = final_skill_state
        generated_content = final_skill_state.get("final_generated_content")
        
        return {
            "final_result": final_result,
            "final_generated_content": generated_content,
            "retrieved_text_chunks": final_skill_state.get("retrieved_text_chunks", []),  # ✅ 傳遞 RAG 資料
            "parent_task_id": state.get("current_task_id"),
            "iteration_count": current_iteration,
            "_router_output": {
                "status": "success",
                "content_generated": bool(generated_content),
                "iteration": current_iteration
            }
        }

    except Exception as e:
        return {"error": str(e)}


# --- Multi-Critic Helper Functions ---

def _format_content_for_ragas(
    content: List[Dict], 
    query: str, 
    retrieved_contexts: List[str]
) -> dict:
    """
    將教材內容格式化為 Ragas 評估格式
    
    重要：Ragas 設計用於評估自然語言對話，因此需要將 JSON 結構
    轉換為易讀的純文字格式，讓 Ragas 能夠正確提取「陳述」並比對證據。
    
    Args:
        content: 生成的內容（exam questions or summary）
        query: 使用者原始查詢
        retrieved_contexts: RAG 檢索結果
    
    Returns:
        {
            "user_input": str,
            "response": str,
            "retrieved_contexts": List[str]
        }
    """
    import json
    
    # 計算總題數並轉換為純文字格式
    response_parts = []
    total_questions = 0
    
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                # 處理選擇題格式
                if item.get("type") == "multiple_choice" and "questions" in item:
                    questions = item["questions"]
                    total_questions += len(questions)
                    
                    for q in questions:
                        q_text_parts = []
                        q_text_parts.append(f"題目 {q.get('question_number', '?')}: {q.get('question_text', '')}")
                        
                        # 選項
                        options = q.get('options', {})
                        if options:
                            q_text_parts.append("選項:")
                            for opt_key in sorted(options.keys()):
                                q_text_parts.append(f"  {opt_key}. {options[opt_key]}")
                        
                        # 正確答案
                        correct_ans = q.get('correct_answer', 'N/A')
                        q_text_parts.append(f"正確答案: {correct_ans}")
                        
                        # 來源證據
                        source = q.get('source', {})
                        if source:
                            page = source.get('page_number', 'N/A')
                            evidence = source.get('evidence', 'N/A')
                            q_text_parts.append(f"來源頁碼: {page}")
                            q_text_parts.append(f"來源證據: {evidence}")
                        
                        response_parts.append("\n".join(q_text_parts))
                
                # 處理是非題格式
                elif item.get("type") == "true_false" and "questions" in item:
                    questions = item["questions"]
                    total_questions += len(questions)
                    
                    for q in questions:
                        q_text_parts = []
                        q_text_parts.append(f"題目 {q.get('question_number', '?')}: {q.get('statement_text', '')}")
                        q_text_parts.append(f"正確答案: {q.get('correct_answer', 'N/A')}")
                        
                        source = q.get('source', {})
                        if source:
                            page = source.get('page_number', 'N/A')
                            evidence = source.get('evidence', 'N/A')
                            q_text_parts.append(f"來源頁碼: {page}")
                            q_text_parts.append(f"來源證據: {evidence}")
                        
                        response_parts.append("\n".join(q_text_parts))
                
                # 處理簡答題格式
                elif item.get("type") == "short_answer" and "questions" in item:
                    questions = item["questions"]
                    total_questions += len(questions)
                    
                    for q in questions:
                        q_text_parts = []
                        q_text_parts.append(f"題目 {q.get('question_number', '?')}: {q.get('question_text', '')}")
                        q_text_parts.append(f"參考答案: {q.get('sample_answer', 'N/A')}")
                        
                        source = q.get('source', {})
                        if source:
                            page = source.get('page_number', 'N/A')
                            evidence = source.get('evidence', 'N/A')
                            q_text_parts.append(f"來源頁碼: {page}")
                            q_text_parts.append(f"來源證據: {evidence}")
                        
                        response_parts.append("\n".join(q_text_parts))
                
                # 處理 summary 格式
                elif "sections" in item:
                    sections = item["sections"]
                    total_questions = len(sections)  # For summaries, count sections
                    for section in sections:
                        response_parts.append(str(section))
    
    # 拼接為純文字 response
    if total_questions > 0:
        response_text = f"【總共生成了 {total_questions} 題】\n\n" + "\n\n".join(response_parts)
    else:
        # Fallback: 如果無法解析，使用 JSON 格式
        response_text = f"【無法解析題目格式，顯示原始資料】\n\n{json.dumps(content, ensure_ascii=False, indent=2)}"
    
    # 格式化 contexts - 保持分段以便 Ragas 比對
    contexts = []
    for chunk in retrieved_contexts:
        if isinstance(chunk, dict):
            # 提取 text (RAG agent 使用的欄位) 或 chunk_text 或 content
            text = chunk.get("text") or chunk.get("chunk_text") or chunk.get("content", "")
        else:
            text = str(chunk)
        if text:
            contexts.append(text)
    
    return {
        "user_input": query,
        "response": response_text,
        "retrieved_contexts": contexts
    }


async def run_fact_critic(state: TeacherAgentState) -> dict:
    """
    執行 Fact Critic - Ragas 指標 + TaskSatisfaction
    
    評估指標:
    - Faithfulness (事實正確性)
    - TaskSatisfaction (任務符合度)
    
    Returns:
        與 quality_critic 對齊的格式:
        {
            "evaluations": [
                {
                    "criteria": "Faithfulness",
                    "analysis": str,
                    "rating": int (1-5),
                    "suggestions": List[str]
                },
                {
                    "criteria": "TaskSatisfaction",
                    "analysis": str,
                    "rating": int (1-5),
                    "suggestions": List[str],
                    "checks": List[Dict]
                }
            ],
            "is_passed": bool,
            "failed_criteria": List[str]
        }
    """
    from backend.app.agents.teacher_agent.critics.fact_critic import (
        CustomFaithfulness, 
        TaskSatisfaction,
        get_fact_critic_llm
    )
    
    # 初始化 metrics
    llm = get_fact_critic_llm()
    
    faithfulness_metric = CustomFaithfulness(llm=llm)
    
    # 準備評估數據
    content = state.get("final_generated_content", [])
    retrieved_contexts = state.get("retrieved_text_chunks", [])
    user_query = state.get("user_query", "")
    
    # Map next_node to task_name for TaskSatisfaction
    next_node = state.get("next_node", "")
    task_name_mapping = {
        "exam_generation_skill": "exam_generation",
        "summarization_skill": "summary",
        "general_chat_skill": "generic"
    }
    task_name = task_name_mapping.get(next_node, "generic")
    
    # --- Debug Logging: Dump contexts to file for manual inspection ---
    try:
        import json
        debug_data = {
            "job_id": state.get("job_id"),
            "task_name": task_name,
            "user_query": user_query,
            "generated_content_preview": str(content)[:500],
            "retrieved_contexts_count": len(retrieved_contexts),
            "retrieved_contexts": retrieved_contexts
        }
        with open(f"/home/monica/Cook.ai/backend/rag_debug_last_run.json", "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Dumped RAG debug data to /home/monica/Cook.ai/backend/rag_debug_last_run.json")
    except Exception as e:
        logger.warning(f"Failed to dump RAG debug data: {e}")
    # ------------------------------------------------------------------
    
    # 將內容格式化為 Ragas 格式
    eval_data = _format_content_for_ragas(content, user_query, retrieved_contexts)
    
    logger.info(f"📐 Fact Critic - contexts: {len(eval_data['retrieved_contexts'])}")
    
    # 1. 執行 Faithfulness 評估 (由 Ragas 提供事實性檢查)
    faithfulness_result = await faithfulness_metric.score_with_feedback(eval_data)
    
    logger.info(f"📐 Fact Critic Results - Faithfulness: {faithfulness_result['normalized_score']}/5")
    
    # 使用標準化分數判斷是否通過（閾值：4 分）
    NORMALIZED_THRESHOLD = 4
    faithfulness_passed = faithfulness_result["normalized_score"] >= NORMALIZED_THRESHOLD
    
    # 僅包含 Faithfulness 檢核項
    evaluations = [
        {
            "criteria": "Faithfulness",
            "analysis": faithfulness_result["analysis"],
            "rating": faithfulness_result["normalized_score"],
            "suggestions": faithfulness_result["suggestions"],
            "raw_ragas_score": faithfulness_result["score"],
            "raw_linear_score": faithfulness_result["raw_linear_score"]
        }
    ]
    
    failed_criteria = []
    if not faithfulness_passed:
        failed_criteria.append("Faithfulness")
    
    # Aggregate token usage
    total_prompt_tokens = faithfulness_result.get("prompt_tokens", 0)
    total_completion_tokens = faithfulness_result.get("completion_tokens", 0)
    model_name = faithfulness_result.get("model_name") or "unknown"

    return {
        "evaluations": evaluations,
        "is_passed": faithfulness_passed,
        "failed_criteria": failed_criteria,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "model_name": model_name
    }


async def run_quality_critic(state: TeacherAgentState) -> dict:
    """
    執行 Quality Critic - G-eval 框架
    
    從現有 run_critics_node 邏輯中抽取
    
    Returns:
        {
            "evaluations": [...],  # 統一格式
            "is_passed": bool,
            "failed_criteria": List[str]
        }
    """
    from backend.app.agents.teacher_agent.critics.quality_critic import QualityCritic
    from backend.app.agents.teacher_agent.skills.exam_generator.nodes import get_llm
    
    job_id = state.get("job_id")
    mode = state.get("critic_mode", "quick")
    
    # Get generated content from state
    final_result = state.get("final_result")
    if not final_result:
        raise Exception(f"No final_result in state for job_id {job_id}")
    
    # Build content structure for critic based on skill type
    next_node = state.get("next_node")
    
    if next_node == "exam_generation_skill":
        exam_data = final_result.get("final_generated_content")
        if not exam_data or not isinstance(exam_data, list):
            raise Exception("No exam content found in final_result")
        
        # Parse exam questions
        all_questions = []
        for question_block in exam_data:
            question_type = question_block.get("type", "unknown")
            questions = question_block.get("questions", [])
            for q in questions:
                q["question_type"] = question_type
            all_questions.extend(questions)
        
        exam = {"type": "exam", "questions": all_questions}
        content_to_eval = exam
        eval_type = "exam"
        
    elif next_node == "summarization_skill":
        summary_content = final_result.get("final_generated_content")
        if not summary_content:
            raise Exception("No summary content found in final_result")
        
        content_to_eval = {
            "type": "summary",
            "content": summary_content.get("sections", [])
        }
        eval_type = "summary"
    else:
        raise Exception(f"Unsupported skill type: {next_node}")
    
    # Get RAG context from state (same as fact_critic)
    rag_chunks = state.get("retrieved_text_chunks", [])
    rag_content = None
    if rag_chunks:
        # Convert to format expected by quality_critic
        combined = []
        for c in rag_chunks:
            if isinstance(c, dict):
                page_nums = c.get('source_pages', [])
                page_str = f"[頁 {', '.join(map(str, page_nums))}]" if page_nums else "[頁 ?]"
                text = c.get('text', '')
                combined.append(f"{page_str} {text}")
            else:
                combined.append(str(c))
        rag_content = "\n\n".join(combined)
        
        # Debug logging
        logger.info(f"✨ Quality Critic - RAG data:")
        logger.info(f"  - Retrieved chunks count: {len(rag_chunks)}")
        if rag_chunks:
            logger.info(f"  - First chunk preview: {combined[0][:100]}...")
    
    # Initialize critic
    llm = get_llm()
    critic = QualityCritic(llm=llm, threshold=4.0)
    user_query = state.get("user_query", "")
    
    # Run evaluation
    if eval_type == "exam":
        evaluation = await critic.evaluate_exam(
            exam=content_to_eval,
            rag_content=rag_content,
            mode=mode,
            user_query=user_query
        )
    else:  # summary
        if rag_content:
            content_to_eval["rag_content"] = rag_content
            
        raw_evaluation = await critic.evaluate(
            content=content_to_eval,
            criteria=None,
            user_query=user_query
        )
        # Wrap for compatibility
        evaluation = {
            "mode": "quick",
            "overall": raw_evaluation,
            "per_question": [],
            "statistics": {"note": "Summary evaluation"},
            "prompt_tokens": raw_evaluation.get("prompt_tokens", 0),
            "completion_tokens": raw_evaluation.get("completion_tokens", 0),
            "model_name": raw_evaluation.get("model_name", "unknown")
        }
    
    # Extract evaluations (already in standard format)
    evaluations = evaluation.get("overall", {}).get("evaluations", [])
    
    # Determine pass/fail
    is_passed = all(e.get("rating", 0) >= 4.0 for e in evaluations)
    failed_criteria = [e["criteria"] for e in evaluations if e.get("rating", 0) < 4.0]
    
    return {
        "evaluations": evaluations,
        "is_passed": is_passed,
        "failed_criteria": failed_criteria,
        "prompt_tokens": evaluation.get("prompt_tokens", 0),
        "completion_tokens": evaluation.get("completion_tokens", 0),
        "model_name": evaluation.get("model_name", "unknown")
    }


def _aggregate_metrics(critics_results: Dict) -> dict:
    """
    綜合多個 critic 的指標
    
    Args:
        critics_results: {
            "fact": {"evaluations": [...], "is_passed": bool, ...},
            "quality": {"evaluations": [...], "is_passed": bool, ...}
        }
    
    Returns:
        {
            "is_passed": bool,
            "failed_critics": ["fact", "quality"],
            "failed_criteria": ["Faithfulness", "Understandable"],
            "all_evaluations": [...],  # 所有評估項目的統一格式
            "improvement_suggestions": str
        }
    """
    is_passed = all(r.get("is_passed", False) for r in critics_results.values())
    
    failed_critics = [
        name for name, result in critics_results.items()
        if not result.get("is_passed", False)
    ]
    
    # 收集所有失敗的標準
    failed_criteria = []
    for result in critics_results.values():
        failed_criteria.extend(result.get("failed_criteria", []))
    failed_criteria = list(set(failed_criteria))
    
    # 合併所有 evaluations (統一格式)
    all_evaluations = []
    for critic_name, result in critics_results.items():
        for eval_item in result.get("evaluations", []):
            all_evaluations.append({
                "critic_type": critic_name,  # "fact" or "quality"
                **eval_item  # criteria, analysis, rating, suggestions
            })
    
    # 合併建議
    suggestions = _combine_suggestions(critics_results)
    
    return {
        "is_passed": is_passed,
        "failed_critics": failed_critics,
        "failed_criteria": failed_criteria,
        "all_evaluations": all_evaluations,  # 統一格式的所有評估
        "improvement_suggestions": suggestions
    }


def _combine_suggestions(critics_results: Dict) -> str:
    """合併所有 critics 的建議 (從 evaluations 中提取)"""
    suggestions = []
    
    for critic_name, result in critics_results.items():
        if not result.get("is_passed"):
            # 從 evaluations 中提取 suggestions
            for eval_item in result.get("evaluations", []):
                criteria = eval_item.get("criteria", "Unknown")
                item_suggestions = eval_item.get("suggestions", [])
                
                if item_suggestions:
                    for s in item_suggestions:
                        suggestions.append(
                            f"在 {criteria} 指標中，{s}"
                        )
    
    return "\n".join(suggestions)


# --- Fact Critic Node ---

@log_task(
    agent_name="fact_critic",
    input_extractor=lambda state: {"job_id": state.get("job_id"), "iteration": state.get("iteration_count", 1)}
)
async def fact_critic_node(state: TeacherAgentState) -> dict:
    """Run Ragas-based fact critic. Saves to task_evaluations with stage=1."""
    import time
    from backend.app.agents.teacher_agent.critics.critic_db_utils import save_critic_evaluation_to_db
    
    logger.info("📐 Running Fact Critic (Ragas)...")
    start_time = time.perf_counter()
    
    try:
        fact_result = await run_fact_critic(state)
        is_passed = fact_result.get("is_passed", False)
        if is_passed:
            logger.info("✅ Fact Critic passed")
        else:
            logger.info(f"❌ Fact Critic failed: {fact_result.get('failed_criteria')}")        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        task_id = state.get("current_task_id")
        job_id = state.get("job_id")
        next_node = state.get("next_node", "")
        critic_mode = state.get("critic_mode", "quick")
        evaluation_mode = f"exam_{critic_mode}" if "exam" in next_node else f"summary_{critic_mode}"
        
        save_critic_evaluation_to_db(
            task_id=task_id, job_id=job_id, evaluation_stage=1,
            evaluation_result=fact_result, is_passed=is_passed,
            feedback={"evaluations": fact_result.get("evaluations", [])},
            metrics_detail={
                "overall_passed": bool(is_passed),
                "scores": {eval["criteria"]: eval["rating"] for eval in fact_result.get("evaluations", [])}
            },
            duration_ms=duration_ms, evaluation_mode=evaluation_mode,
            iteration_number=state.get("iteration_count", 1)
        )
        
        # Calculate cost
        prompt_tokens = fact_result.get("prompt_tokens", 0)
        completion_tokens = fact_result.get("completion_tokens", 0)
        model_name = fact_result.get("model_name", "gpt-4o-mini")
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        return {
            "fact_passed": bool(is_passed),
            "fact_feedback": {"evaluations": fact_result.get("evaluations", [])},
            "fact_metrics": {
                "overall_passed": bool(is_passed),
                "scores": {eval["criteria"]: eval["rating"] for eval in fact_result.get("evaluations", [])}
            },
            "fact_failed_criteria": fact_result.get("failed_criteria", []),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name
        }
    except Exception as e:
        logger.error(f"ERROR in fact_critic: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "fact_passed": False}


# --- Quality Critic Node ---

@log_task(
    agent_name="quality_critic",
    input_extractor=lambda state: {"job_id": state.get("job_id"), "iteration": state.get("iteration_count", 1)}
)
async def quality_critic_node(state: TeacherAgentState) -> dict:
    """Run G-Eval quality critic. Saves to task_evaluations with stage=2."""
    import time
    from backend.app.agents.teacher_agent.critics.critic_db_utils import save_critic_evaluation_to_db
    
    logger.info("✨ Running Quality Critic (G-Eval)...")
    start_time = time.perf_counter()
    
    try:
        quality_result = await run_quality_critic(state)
        is_passed = quality_result.get("is_passed", False)
        if is_passed:
            logger.info("✅ Quality Critic passed")
        else:
            logger.info(f"❌ Quality Critic failed: {quality_result.get('failed_criteria')}")        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        task_id = state.get("current_task_id")
        job_id = state.get("job_id")
        next_node = state.get("next_node", "")
        critic_mode = state.get("critic_mode", "quick")
        evaluation_mode = f"exam_{critic_mode}" if "exam" in next_node else f"summary_{critic_mode}"
        
        save_critic_evaluation_to_db(
            task_id=task_id, job_id=job_id, evaluation_stage=2,
            evaluation_result=quality_result, is_passed=is_passed,
            feedback={"evaluations": quality_result.get("evaluations", [])},
            metrics_detail={
                "overall_passed": bool(is_passed),
                "scores": {eval["criteria"]: eval["rating"] for eval in quality_result.get("evaluations", [])}
            },
            duration_ms=duration_ms, evaluation_mode=evaluation_mode,
            iteration_number=state.get("iteration_count", 1)
        )
        
        # Calculate cost
        prompt_tokens = quality_result.get("prompt_tokens", 0)
        completion_tokens = quality_result.get("completion_tokens", 0)
        model_name = quality_result.get("model_name", "gpt-4o-mini")
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        return {
            "quality_passed": bool(is_passed),
            "quality_feedback": {"evaluations": quality_result.get("evaluations", [])},
            "quality_metrics": {
                "overall_passed": bool(is_passed),
                "scores": {eval["criteria"]: eval["rating"] for eval in quality_result.get("evaluations", [])}
            },
            "quality_failed_criteria": quality_result.get("failed_criteria", []),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name
        }
    except Exception as e:
        logger.error(f"ERROR in quality_critic: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "quality_passed": False}


# --- Multi-Critic Evaluation Node ---

async def run_critics_node(state: TeacherAgentState) -> dict:
    """
    根據 enabled_critics 依序執行對應的 critic
    
    支持 4 種實驗 workflow:
    - [] : Workflow 1 (不應該到這，會被 bypass)
    - ["fact"] : Workflow 2 (只用 Ragas 指標)
    - ["quality"] : Workflow 3 (只用 G-eval 指標)
    - ["fact", "quality"] : Workflow 4 (兩者皆用)
    
    執行順序: Fact → Quality (優先檢查事實正確性)
    """
    import time
    from backend.app.agents.teacher_agent.critics.critic_db_utils import save_evaluation_to_db
    from backend.app.agents.teacher_agent.critics.critic_formatters import EvaluationFormatter
    from backend.app.utils.db_logger import TAIPEI_TZ
    
    job_id = state.get("job_id")
    iteration = state.get("iteration_count", 1)
    enabled_critics = state.get("enabled_critics", ["quality"])
    
    logger.info(f"Starting evaluation (Iteration {iteration})")
    logger.info(f"Job ID: {job_id}")
    logger.info(f"Enabled critics: {enabled_critics}")
    
    start_time = time.perf_counter()
    
    try:
        critics_results = {}
        overall_passed = True
        
        # 1. 執行 Fact Critic (優先) ⚠️
        if "fact" in enabled_critics:
            logger.info("📐 Running Fact Critic (Ragas)...")
            fact_result = await run_fact_critic(state)
            critics_results["fact"] = fact_result
            
            if not fact_result.get("is_passed"):
                overall_passed = False
                logger.warning(f"❌ Fact Critic failed: {fact_result.get('failed_criteria')}")
            else:
                logger.info("✅ Fact Critic passed")
        
        # 2. 執行 Quality Critic
        if "quality" in enabled_critics:
            logger.info("✨ Running Quality Critic (G-eval)...")
            quality_result = await run_quality_critic(state)
            critics_results["quality"] = quality_result
            
            if not quality_result.get("is_passed"):
                overall_passed = False
                logger.warning(f"❌ Quality Critic failed: {quality_result.get('failed_criteria')}")
            else:
                logger.info("✅ Quality Critic passed")
        
        # 3. 構建綜合 feedback
        combined_feedback = {
            "iteration": iteration,
            "critics": critics_results,
            "overall_passed": overall_passed,
            "timestamp": datetime.now(TAIPEI_TZ).isoformat()
        }
        
        # 4. 聚合指標
        aggregated_metrics = _aggregate_metrics(critics_results)
        
        # 5. 更新 feedback history
        feedback_history = state.get("critic_feedback", [])
        feedback_history.append(combined_feedback)
        
        logger.info(f"📊 Iteration {iteration} evaluation complete: {'✅ Passed' if overall_passed else '❌ Failed'}")
        logger.info(f"   Failed critics: {aggregated_metrics.get('failed_critics', [])}")
        logger.info(f"   Failed criteria: {aggregated_metrics.get('failed_criteria', [])}")
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # 6. 為資料庫準備格式化資料 (兼容現有格式)
        # 構建與舊格式兼容的 evaluation 結構
        db_evaluation = {
            "mode": state.get("critic_mode", "quick"),
            "overall": {
                "evaluations": aggregated_metrics.get("all_evaluations", [])
            },
            "per_question": [],  # Multi-critic 模式下不提供逐題評估
            "statistics": {
                "note": "Multi-critic evaluation",
                "enabled_critics": enabled_critics,
                "failed_critics": aggregated_metrics.get("failed_critics", [])
            }
        }
        
        # 格式化 feedback (用於 revise agent)
        feedback_for_generator = {
            "is_passed": overall_passed,
            "failed_criteria": aggregated_metrics.get("failed_criteria", []),
            "improvement_suggestions": aggregated_metrics.get("improvement_suggestions", ""),
            "all_evaluations": aggregated_metrics.get("all_evaluations", [])
        }
        
        # 格式化 metrics (用於實驗分析)
        metrics_detail = {
            "is_passed": overall_passed,
            "failed_critics": aggregated_metrics.get("failed_critics", []),
            "failed_criteria": aggregated_metrics.get("failed_criteria", []),
            "all_evaluations": aggregated_metrics.get("all_evaluations", []),
            "duration_ms": duration_ms,
            "enabled_critics": enabled_critics,
            "mode": state.get("critic_mode", "quick")
        }
        
        # 7. 儲存到資料庫
        parent_task_id = state.get("parent_task_id")
        next_node = state.get("next_node")
        
        # 判斷 evaluation_mode
        if next_node == "exam_generation_skill":
            evaluation_mode = f"exam_{state.get('critic_mode', 'quick')}"
        elif next_node == "summarization_skill":
            evaluation_mode = f"summary_{state.get('critic_mode', 'quick')}"
        else:
            evaluation_mode = "unknown"
        
        # 加入 multi-critic 標記
        evaluation_mode = f"multi_{evaluation_mode}" if len(enabled_critics) > 1 else evaluation_mode
        
        save_result = save_evaluation_to_db(
            job_id=job_id,
            parent_task_id=parent_task_id,
            evaluation_result=db_evaluation,
            duration_ms=duration_ms,
            is_passed=overall_passed,
            feedback=feedback_for_generator,
            metrics_detail=metrics_detail,
            evaluation_mode=evaluation_mode,
            iteration_number=state.get("iteration_count", 1)
        )
        
        if save_result:
            eval_task_id, task_eval_id = save_result
            logger.info(f"Saved evaluation (task_id={eval_task_id}, eval_id={task_eval_id})")
        
        # 8. 返回評估結果到 state
        # 不再在這裡遞增 iteration_count！由 generator 節點負責
        # 確保所有值都是 JSON 可序列化的
        return {
            "critic_passed": bool(overall_passed),  # 確保是 Python bool
            "critic_feedback": feedback_history,
            "critic_metrics": aggregated_metrics,
            # Router metadata for cleaner database output
            "_router_output": {
                "status": "completed",
                "passed": bool(overall_passed),
                "iteration": state.get("iteration_count", 1),
                "enabled_critics": enabled_critics,
                "failed_criteria": [c for c, passed in aggregated_metrics.items() if not passed] if not overall_passed else []
            }
        }
        
    except Exception as e:
        import traceback
        logger.error(f"ERROR in multi-critic evaluation: {str(e)}")
        traceback.print_exc()
        return {"error": f"Multi-critic evaluation failed: {str(e)}"}


# --- Conditional Edge for Critic ---

def should_continue_from_critic(state: TeacherAgentState) -> str:
    """
    決定 critic 之後的流向
    聚合 fact_critic 和 quality_critic 的结果
    """
    # 1. 聚合两个 critics 的结果
    # IMPORTANT: Only check critics that were actually run (not default to True!)
    enabled_critics = state.get("enabled_critics", [])
    
    # Check only enabled critics
    critics_to_check = []
    if "fact" in enabled_critics:
        fact_passed = state.get("fact_passed")
        if fact_passed is None:
            logger.error("ERROR: fact_critic was enabled but fact_passed is None!")
            fact_passed = False  # Fail safe
        critics_to_check.append(("fact", fact_passed))
    
    if "quality" in enabled_critics:
        quality_passed = state.get("quality_passed")
        if quality_passed is None:
            logger.error("ERROR: quality_critic was enabled but quality_passed is None!")
            quality_passed = False  # Fail safe
        critics_to_check.append(("quality", quality_passed))
    
    # Overall passed = all enabled critics passed
    overall_passed = all(passed for _, passed in critics_to_check) if critics_to_check else True
    

    
    if overall_passed:
        logger.info("✅ All critics passed, proceeding to output")
        return "aggregate_output"
    
    # 2. 檢查迭代次數
    current_iteration = state.get("iteration_count", 1)
    max_iter = state.get("max_iterations", 3)
    
    # 如果當前已經是最後一次，不再 loop
    if current_iteration >= max_iter:
        logger.warning(f"⚠️ Max iterations ({max_iter}) reached at iteration {current_iteration}")
        logger.info("Proceeding to output with partial success status")
        return "aggregate_output"
    
    # 3. 動態檢查 skill 是否支持 refinement
    last_skill = state.get("next_node")
    skill_config = SKILL_CONFIGS.get(last_skill)
    
    if skill_config and skill_config.supports_refinement:
        # Increment iteration_count for next refinement round
        next_iteration = current_iteration + 1
        logger.info(f"🔄 Iteration {next_iteration}: Returning to {last_skill}")
        logger.info(f"   Strategy: {skill_config.refinement_strategy}")
        # Update state with incremented iteration
        state["iteration_count"] = next_iteration
        return last_skill

    else:
        logger.warning(f"⚠️ Skill {last_skill} doesn't support refinement")
        logger.info("Ending loop and proceeding to output")
        return "aggregate_output"


# --- Final Aggregation Node ---

def aggregate_output_node(state: TeacherAgentState) -> dict:
    job_id = state['job_id']
    next_node = state.get("next_node")
    
    final_api_response = {"job_id": job_id}
    
    # Check for critical errors from previous nodes
    if state.get("error"):
        db_logger.update_job_status(job_id, 'failed', error_message=state["error"])
        final_api_response["display_type"] = "text_message"
        final_api_response["content"] = {"message": "Job failed due to a critical error.", "error_details": state["error"]}
        return final_api_response

    final_result = state.get("final_result")

    # Format the final result based on the skill used for DB logging
    db_title = None

    if next_node == "general_chat_skill":
        if final_result and isinstance(final_result, dict) and "content" in final_result:
            final_api_response["display_type"] = "text_message"
            final_api_response["title"] = final_result.get('title', "Cook AI 助教回覆")
            final_api_response["content"] = final_result.get('content')

            db_title = final_result.get("title", "Cook AI 助教回覆")
        else:
            final_api_response["display_type"] = "text_message"
            final_api_response["content"] = {
                "message": "General chat skill executed, but no content was generated.",
                "debug_final_result": str(final_result)
            }
            
    elif next_node == "summarization_skill":
        # final_result is the entire state from the summarization_app.invoke()
        summary_content = final_result.get("final_generated_content")
        
        if (summary_content and isinstance(summary_content, dict) and 
            summary_content.get("type") == "summary" and 
            "title" in summary_content and "sections" in summary_content):
            
            final_api_response["display_type"] = "summary_report"
            final_api_response["title"] = summary_content.get("title", "教材摘要")
            final_api_response["content"] = summary_content
            db_title = summary_content.get("title", "教材摘要")
        else:
            final_api_response["display_type"] = "text_message"
            final_api_response["content"] = {
                "message": "Summarization skill executed, but the final_result was not in the expected format.",
                "debug_final_result": str(final_result)
            }
            
    elif next_node == "exam_generation_skill":
        main_title = final_result.get("main_title") if isinstance(final_result, dict) else None
        exam_data = final_result.get("final_generated_content") if isinstance(final_result, dict) else final_result
        
        if exam_data and isinstance(exam_data, list) and len(exam_data) > 0:
            # Flatten blocks into a single questions list for a leaner JSONB structure
            all_questions = []
            for item in exam_data:
                # Case A: Item is a block of questions (e.g. from AI generator)
                if isinstance(item, dict) and "questions" in item:
                    block_type = item.get("type")
                    for q in item["questions"]:
                        # Ensure each question carries its own type information
                        if "type" not in q: q["type"] = block_type
                        if "question_type" not in q: q["question_type"] = block_type
                        all_questions.append(q)
                # Case B: Item is already an individual question (standalone)
                else:
                    all_questions.append(item)
            
            final_api_response["display_type"] = "exam_questions"
            final_api_response["title"] = main_title if main_title else f"未命名測驗 ({get_now_taipei().strftime('%Y-%m-%d')})"
            
            # Use the flat list directly as the content
            final_api_response["content"] = all_questions
            db_title = final_api_response["title"]
        else:
            final_api_response["display_type"] = "text_message"
            final_api_response["content"] = {
                "message": "Exam generation ran, but no content was passed from the skill.",
                "debug_final_result": str(final_result)
            }
            
    else: # Fallback for unknown skills
        final_api_response["display_type"] = "text_message"
        final_api_response["content"] = {"message": f"Unknown skill '{next_node}' executed or no content generated."}

    # 統一資料庫儲存邏輯：儲存 content 部分
    if db_title and final_api_response.get("display_type") != "text_message":
        if state.get("ablation_group"):
            logger.info(f"Skipping save_generated_content to generated_contents because this is ablation run: {state.get('ablation_group')}")
        else:
            try:
                task_id = state.get("current_task_id")
                final_content_type = final_api_response.get("display_type", "unknown")
                
                content_id = None
                if task_id:
                    # ✅ FIX: Only save the content part, not the entire final_api_response
                    # This avoids nested structure (content.content.content....)
                    content_to_save = final_api_response.get("content", {})
                    
                    content_id = db_logger.save_generated_content(
                        task_id=task_id,
                        content_type=final_content_type,
                        title=db_title,
                        content=content_to_save,  # Only save content, not entire response
                        author_id=state.get("user_id")  # ✅ Pass user_id as author_id
                    )

                if content_id:
                    db_logger.update_job_final_output(job_id, content_id)
                else:
                    logger.warning("Could not save final content, current_task_id not found or content generation failed.")

            except Exception as e:
                logger.error(f"Failed to save final content for {next_node}. Reason: {e}")
            

    # Update the main job status to completed if it wasn't already failed
    current_job_status = db_logger.get_job_status(job_id)
    if current_job_status not in ['failed', 'partial_success', 'completed']:
        db_logger.update_job_status(job_id, 'completed')
    
    return {
    "final_result": final_api_response,
    "parent_task_id": state.get("current_task_id")  # Propagate parent_task_id
    }

# --- Helper: Dynamic Graph Construction ---

def build_skill_to_critic_edges(builder: StateGraph, skill_configs: Dict):
    """
    根據 skill 配置動態建立 edges
    Supports dynamic routing to critics based on enabled_critics.
    """
    def route_to_first_critic(state: TeacherAgentState) -> str:
        """根據 enabled_critics 決定第一個要執行的 critic"""
        enabled_critics = state.get("enabled_critics", ["quality"])
        if "fact" in enabled_critics:
            return "fact_critic"
        elif "quality" in enabled_critics:
            return "quality_critic"
        else:
            return "aggregate_output"
    
    for skill_name, config in skill_configs.items():
        if config.supports_critic:
            # 需要 critic 的 skill → 動態路由到第一個 critic
            builder.add_conditional_edges(
                skill_name,
                route_to_first_critic,
                {"fact_critic": "fact_critic", "quality_critic": "quality_critic", "aggregate_output": "aggregate_output"}
            )
            logger.info(f"✓ {skill_name} → [dynamic critic routing]")
        else:
            # 不需要 critic 的 skill → aggregate_output
            builder.add_edge(skill_name, "aggregate_output")
            logger.info(f"✓ {skill_name} → aggregate_output (bypass critic)")

# --- Graph Definition ---

builder = StateGraph(TeacherAgentState)

# Add the nodes
builder.add_node("router", router_node)
builder.add_node("exam_generation_skill", exam_skill_node)
builder.add_node("general_chat_skill", general_chat_node)
builder.add_node("summarization_skill", summarization_skill_node)
builder.add_node("fact_critic", fact_critic_node)
builder.add_node("quality_critic", quality_critic_node)
builder.add_node("aggregate_output", aggregate_output_node)

# Set the entry point
builder.set_entry_point("router")

# Add the conditional edge from the router to the skills
builder.add_conditional_edges(
    "router",
    should_continue,
    {
        "exam_generation_skill": "exam_generation_skill",
        "general_chat_skill": "general_chat_skill",
        "summarization_skill": "summarization_skill",
    },
)

#  Connect skills to critic or aggregate (dynamic based on skill config) ✅
build_skill_to_critic_edges(builder, SKILL_CONFIGS)

# Fact critic routing: if quality also enabled -> quality_critic, else check continue
def route_after_fact_critic(state: TeacherAgentState) -> str:
    enabled_critics = state.get("enabled_critics", [])
    if "quality" in enabled_critics:
        return "quality_critic"
    return should_continue_from_critic(state)

builder.add_conditional_edges(
    "fact_critic",
    route_after_fact_critic,
    {
        "quality_critic": "quality_critic",
        "aggregate_output": "aggregate_output",
        "exam_generation_skill": "exam_generation_skill",
        "summarization_skill": "summarization_skill"
    }
)

# Quality critic: always check should_continue_from_critic
builder.add_conditional_edges(
    "quality_critic",
    should_continue_from_critic,
    {
        "aggregate_output": "aggregate_output",
        "exam_generation_skill": "exam_generation_skill",
        "summarization_skill": "summarization_skill"
    }
)

# The aggregation node is the final step
builder.add_edge("aggregate_output", END)

# Compile the graph with increased recursion limit
app = builder.compile(
    checkpointer=None,  # No checkpointing needed for now
    debug=False
)

# Set recursion limit in config
# Note: This will be passed when invoking the graph
DEFAULT_CONFIG = {"recursion_limit": 100}  # Increased from default 25