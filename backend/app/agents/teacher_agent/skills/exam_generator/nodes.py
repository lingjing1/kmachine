import os
import json
import time
from datetime import datetime # Add this import
import random
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .state import ExamGenerationState
from backend.app.agents.teacher_agent.rag_agent import rag_agent
from backend.app.utils import db_logger # Add this import
from backend.app.utils.db_logger import log_task, log_task_sources
from backend.app.core.prompt_manager import prompt_manager
from backend.app.config.settings import settings

# --- Pydantic Models for Tool-based Planning ---
class Task(BaseModel):
    """A single task for generating questions."""
    type: str = Field(..., description="The type of task. MUST be one of: 'multiple_choice', 'true_false', 'fill_in_blank', 'short_answer'.")
    count: int = Field(..., description="The number of questions to generate for this task.")
    unit_name: Optional[str] = Field(None, description="The specific topic or unit name for this task, if any.")


class Plan(BaseModel):
    """A structured plan consisting of a list of generation tasks."""
    main_title: str = Field(..., description="A concise, professional title (in Traditional Chinese) that clearly describes the topic and focus of the generated exam questions based on the user's query.")
    tasks: List[Task] = Field(..., description="A list of generation tasks to perform based on the user's query.")

# --- Pydantic Models for Question Types ---
class Source(BaseModel):
    page_number: str = Field(..., description="The page number from which the information was sourced.")
    match_score: Optional[int] = Field(None, description="Fuzzy match confidence score (0-100). Inject by validator.")

class MultipleChoiceQuestion(BaseModel):
    question_number: int = Field(..., description="The sequential number of the question.")
    question_text: str = Field(..., description="The text of the multiple-choice question.")
    options: Dict[str, str] = Field(..., description="A dictionary of options, e.g., {'A': 'Option Text A', ...}. MUST contain exactly 4 options: A, B, C, D.")
    correct_answer: str = Field(..., description="The letter corresponding to the correct answer (e.g., 'A', 'B').")
    related_kps: List[str] = Field(default_factory=list, description="List of related knowledge point names.")
    detailed_explanation: str = Field("", description="引導式回饋解析，解釋答案邏輯並釐清可能的典型誤解")

class TrueFalseQuestion(BaseModel):
    question_number: int = Field(..., description="The sequential number of the question.")
    question_text: str = Field(..., description="The statement to be evaluated as true or false.")
    options: Dict[str, str] = Field(default={"true": "正確", "false": "錯誤"}, description="A dictionary with keys 'true' and 'false'. Defaults to 正確/錯誤.")
    correct_answer: str = Field(..., description="The correct answer, either 'true' or 'false'.")
    related_kps: List[str] = Field(default_factory=list, description="List of related knowledge point names.")
    detailed_explanation: str = Field("", description="引導式回饋解析，解釋判斷依據並釐清可能的典型誤解")

class ShortAnswerQuestion(BaseModel):
    question_number: int = Field(..., description="The sequential number of the question.")
    question_text: str = Field(..., description="The text of the short-answer question.")
    sample_answer: str = Field(..., description="A detailed sample correct answer for the question.")
    related_kps: List[str] = Field(default_factory=list, description="List of related knowledge point names.")
    detailed_explanation: str = Field("", description="引導式回饋解析，解釋核心概念並釐清可能的典型誤解")

class FillInBlankQuestion(BaseModel):
    question_number: int = Field(..., description="The sequential number of the question.")
    question_text: str = Field(..., description="The text of the question with '____' indicating the blank.")
    correct_answer: str = Field(..., description="The correct answer that fills the blank.")
    related_kps: List[str] = Field(default_factory=list, description="List of related knowledge point names.")
    detailed_explanation: str = Field("", description="引導式回饋解析，解釋填空邏輯並釐清可能的典型誤解")

# A model to hold a list of questions for a specific type, for tool calling
class MultipleChoiceQuestionsList(BaseModel):
    questions: List[MultipleChoiceQuestion] = Field(..., description="A list of multiple-choice questions.")

class TrueFalseQuestionsList(BaseModel):
    questions: List[TrueFalseQuestion] = Field(..., description="A list of true/false questions.")

class ShortAnswerQuestionsList(BaseModel):
    questions: List[ShortAnswerQuestion] = Field(..., description="A list of short-answer questions.")

class FillInBlankQuestionsList(BaseModel):
    questions: List[FillInBlankQuestion] = Field(..., description="A list of fill-in-the-blank questions.")

from backend.app.agents.teacher_agent.utils.llm_utils import (
    get_llm, call_openai_api, _prepare_multimodal_content, MODEL_PRICING
)

# --- Node Functions ---

from backend.app.utils.db_logger import log_task, log_task_sources
from backend.app.agents.teacher_agent.rag_agent import rag_agent
from backend.app.agents.teacher_agent.utils.rag_utils import calculate_adaptive_top_k

@log_task(
    agent_name="retriever", 
    input_extractor=lambda state: {
        "query": state.get("query"), 
        "unit_name": state.get("unit_name"),
        "source_ids": state.get("source_ids"),
        "selected_kp_names": state.get("selected_kp_names"),
        "generated_source_ids": state.get("generated_source_ids"),
        "ablation_group": state.get("ablation_group")
    }

)
def retrieve_chunks_node(state: ExamGenerationState) -> dict:
    """Retrieves context using RAGAgent and populates the state."""
    try:
        # Dynamic Top-K Allocation
        num_docs = len(state["source_ids"]) + len(state.get("generated_source_ids", []))
        # Phase 1: kp_counts is None. Phase 1.5: Pass kp_counts
        top_k = calculate_adaptive_top_k(num_documents=num_docs if num_docs > 0 else 1)
        
        rag_results = rag_agent.search(
            user_prompt=state["query"], 
            unique_content_ids=state["source_ids"],
            top_k=top_k,
            selected_kp_names=state.get("selected_kp_names"),  # ✅ Pass KP names for Separated Retrieval
            generated_course_content_ids=state.get("generated_source_ids", []),
            ablation_group=state.get("ablation_group")
        )
        enriched_chunks = rag_results["text_chunks"]
        enriched_pages = rag_results["page_content"]

        
        # The decorator has already created the task and injected its ID into the state
        log_task_sources(state["current_task_id"], enriched_chunks)

        return {
            "retrieved_text_chunks": enriched_chunks,
            "retrieved_page_content": enriched_pages,
            "rag_metrics": rag_results.get("rag_metrics", {}), # For task output log
            "generation_plan": [],
            "final_generated_content": [],
            "generation_errors": [],
            "parent_task_id": state["current_task_id"] # Set self as parent for the next node
        }
    except Exception as e:
        return {"error": f"Failed to retrieve context: {str(e)}"}

@log_task(
    agent_name="plan_generation_tasks", 
    input_extractor=lambda state: {
        "query": state.get("query"),
        "unit_name": state.get("unit_name"),
        "critic_suggestions": state.get("critic_feedback", [])[-1].get("suggestions") if state.get("critic_feedback") else None
    }
)
def plan_generation_tasks_node(state: ExamGenerationState) -> dict:
    """Analyzes the user query to create a structured generation plan using an LLM."""
    # --- Refinement Logic ---
    critic_feedback = state.get("critic_feedback", [])
    if critic_feedback:
        latest_feedback = critic_feedback[-1]
        previous_content = state.get("final_generated_content", [])
        
        if previous_content:
            refinement_plan_task = {
                "type": "refine_exam",
                "count": 1, 
                "unit_name": state.get("unit_name") or "根據評估建議進行試卷修正 (Refinement)",

                "params": {
                    "feedback": latest_feedback,
                    "previous_content": previous_content
                }
            }
            
            return {
                "generation_plan": [refinement_plan_task],
                "current_task": None,
                "final_generated_content": previous_content
            }

    # If plan exists and no feedback (or feedback passed), skip
    if state.get("generation_plan") and not critic_feedback:
        return {}
    
    if state.get("final_generated_content") and not critic_feedback:
        return {}

    try:
        llm = get_llm()
        system_prompt = prompt_manager.get_prompt("exam_generator.plan_system")
        user_prompt = prompt_manager.get_prompt(
            "exam_generator.plan_user", 
            user_query=state.get('query', ''),
            unit_name=state.get('unit_name'),
            question_types=state.get('question_types', []),
            question_count=state.get('question_count', 0)
        )
        
        planner_llm = llm.bind_tools(tools=[Plan], tool_choice="Plan")
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        
        response = planner_llm.invoke(messages)
        
        if not response.tool_calls:
            raise ValueError("The model did not call the required 'Plan' tool.")
            
        plan = Plan(**response.tool_calls[0]['args'])

        main_title = plan.main_title
        generation_plan = [task.model_dump() for task in plan.tasks]
        
        # --- Extract tokens and cost for the decorator ---
        token_usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        model_name = llm.model_name
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        return {
            "generation_plan": generation_plan,
            "main_title": main_title,
            "parent_task_id": state["current_task_id"], # Pass self as parent for next nodes
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name  # Add model_name
        }
    except Exception as e:
        error_message = f"Failed to create a generation plan: {e}"
        return {"error": error_message, "generation_errors": [{"task": "plan_generation_tasks", "error_message": str(e)}]}

def prepare_next_task_node(state: ExamGenerationState) -> ExamGenerationState:
    """Pops the next task from the plan and sets it as the current task."""
    state["error"] = None # Clear temporary error for next task
    if state.get("generation_plan") and len(state["generation_plan"]) > 0:
        state["current_task"] = state["generation_plan"].pop(0)
    else:
        state["current_task"] = None
    return state

def should_continue_router(state: ExamGenerationState) -> str:
    """Router that checks the current task and decides where to go next."""
    # If there's a temporary error from the previous task, it's already logged in generation_errors.
    # We want to continue processing other tasks if possible, or go to aggregation.
    current_task = state.get("current_task")
    if current_task:
        task_type = current_task.get("type")
        if task_type == "refine_exam":
            return "refine_exam"
        valid_types = ["multiple_choice", "short_answer", "true_false", "fill_in_blank"]
        return f"generate_{task_type}" if task_type in valid_types else "end"
    return "end"

# --- Refactored Generation Logic ---

def _generic_generate_question(state: ExamGenerationState, task_type_name: str) -> dict:
    """
    A generic internal function that handles question generation.
    It is called by the public-facing, decorated node functions.
    It returns a dictionary with results and metrics for the decorator to log.
    """
    current_task = state.get("current_task", {})
    
    try:
        llm = get_llm()
        task_details = f"Task: Generate {current_task.get('count', 1)} {task_type_name.replace('_', ' ')} question(s)"
        if current_task.get('unit_name'):
            task_details += f" about '{current_task.get('unit_name')}'"

        # 1. Prepare Multimodal Content (Filter out "existing_material" background context)
        original_pages = [
            p for p in state.get("retrieved_page_content", [])
            if p.get("source_category") == "original_document"
        ]
        combined_retrieved_text, image_data_urls = _prepare_multimodal_content(original_pages)
        
        # 2. Determine cognitive strategy based on count
        count = current_task.get("count", 1)
        strategy_key = "exam_generator.bloom_strategies.diverse" if count > 3 else "exam_generator.bloom_strategies.singular"
        cognitive_strategy = prompt_manager.get_prompt(strategy_key)
        
        # 3. Get system prompt with injected strategy
        system_message_content = prompt_manager.get_prompt(
            "exam_generator.qa_system",
            cognitive_strategy=cognitive_strategy
        )
        
        # 4. Get specific type instructions (already unescaped once by PromptManager if needed)
        type_specific_instruction = prompt_manager.get_prompt(f"exam_generator.qa_{task_type_name}_instruction")

        # 5. Prepare KP list for prompt
        selected_kp_names = state.get("selected_kp_names") or []
        kp_list_str = "\n".join([f"- {name}" for name in selected_kp_names]) if selected_kp_names else "無預設知識點（請根據教材自行標註最相關的知識點名稱）"

        # 6. Get final user prompt content in ONE step via get_prompt to ensure safety
        user_prompt_content = prompt_manager.get_prompt(
            "exam_generator.qa_user_template",
            user_query=state.get("query", "Default generate request"),
            task_details=f"Generate {count} {task_type_name} questions.",
            combined_text=combined_retrieved_text,
            type_specific_instruction=type_specific_instruction,
            kp_list=kp_list_str
        )
        
        human_message_content = [{"type": "text", "text": user_prompt_content}]
        
        if image_data_urls:
            for image_uri in image_data_urls:
                human_message_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_uri, "detail": "low"}
                })

        messages = [
            SystemMessage(content=system_message_content),
            HumanMessage(content=human_message_content)
        ]

        tool_model_map = {
            "multiple_choice": MultipleChoiceQuestionsList,
            "true_false": TrueFalseQuestionsList,
            "short_answer": ShortAnswerQuestionsList,
            "fill_in_blank": FillInBlankQuestionsList,
        }
        tool_model = tool_model_map.get(task_type_name)
        if not tool_model:
            raise ValueError(f"Unsupported task type: {task_type_name}")

        tool_llm = llm.bind_tools(tools=[tool_model], tool_choice={"type": "function", "function": {"name": tool_model.__name__}})
        response = tool_llm.invoke(messages)
        
        args = response.tool_calls[0].get('args', {})
        
        # --- JSON Healing Mechanism ---
        # Sometimes LLMs return stringified JSON within the list due to nesting complexity.
        if 'questions' in args and isinstance(args['questions'], list):
            healed_questions = []
            for item in args['questions']:
                if isinstance(item, str):
                    clean_item = item.strip()
                    if (clean_item.startswith('{') and clean_item.endswith('}')) or (clean_item.startswith('[') and clean_item.endswith(']')):
                        try:
                            healed_questions.append(json.loads(clean_item))
                            continue
                        except:
                            pass
                healed_questions.append(item)
            args['questions'] = healed_questions

        try:
            generated_questions_list = tool_model(**args)
        except Exception as ve:
            # Re-raise with type info for better debugging if still failing
            raise ValueError(f"Validation failed for {task_type_name}: {str(ve)}")
        
        # Assign globally unique numeric IDs based on seconds since epoch
        base_id = int(time.time())
        final_generated_content = {
            "type": task_type_name,
            "questions": []
        }
        
        for i, q in enumerate(generated_questions_list.questions):
            q_dict = q.model_dump()
            # If the model didn't provide an ID, or it's non-numeric, assign a unique one
            if "id" not in q_dict or not q_dict["id"]:
                q_dict["id"] = base_id + i
            elif isinstance(q_dict["id"], str) and q_dict["id"].isdigit():
                q_dict["id"] = int(q_dict["id"])
            elif not isinstance(q_dict["id"], int):
                q_dict["id"] = base_id + i
            
            final_generated_content["questions"].append(q_dict)
        
        token_usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        model_name = llm.model_name
        estimated_cost = db_logger.calculate_llm_cost(model_name, prompt_tokens, completion_tokens)

        # The decorator will handle logging the output.
        # We append to a new list to avoid modifying state directly in a deep way.
        
        # === 新增：Citation Validation ===
        # Import moved to top-level or inside function to avoid circular imports if any, 
        # but top-level is cleaner. Assuming standard import at top of file.
        from backend.app.agents.teacher_agent.utils.exam_citation_validator import ExamCitationValidator
        
        # Use retrieved_text_chunks for validation. 
        # Note: state['retrieved_text_chunks'] should be available and enriched.
        retrieved_chunks = state.get("retrieved_text_chunks", [])
        retrieved_pages = state.get("retrieved_page_content", [])
        
        validator = ExamCitationValidator(retrieved_chunks, retrieved_pages)
        validation_result = validator.validate(final_generated_content["questions"])
        
        if not validation_result["valid"]:
            # Optionally log warning or add warning flag
            final_generated_content["citation_validation"] = validation_result
            final_generated_content["generation_quality_warning"] = True
        else:
            final_generated_content["citation_validation"] = validation_result

        new_final_generated_content = state.get("final_generated_content", []) + [final_generated_content]

        return {
            "final_generated_content": new_final_generated_content,
            "main_title": state.get("main_title"), # Preserve the title
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost,
            "model_name": model_name  # Add model_name
        }
    except Exception as e:
        error_message = f"Error in {task_type_name} generation: {str(e)}"
        new_generation_errors = state.get("generation_errors", []) + [{"task_type": task_type_name, "error_message": str(e), "task_input": current_task}]
        return {"error": error_message, "generation_errors": new_generation_errors}

@log_task(agent_name="generate_multiple_choice", input_extractor=lambda state: {"unit_name": state.get("unit_name"), "current_task": state.get("current_task")})
def generate_multiple_choice_node(state: ExamGenerationState) -> dict:
    return _generic_generate_question(state, "multiple_choice")

@log_task(agent_name="generate_short_answer", input_extractor=lambda state: {"unit_name": state.get("unit_name"), "current_task": state.get("current_task")})
def generate_short_answer_node(state: ExamGenerationState) -> dict:
    return _generic_generate_question(state, "short_answer")

@log_task(agent_name="generate_true_false", input_extractor=lambda state: {"unit_name": state.get("unit_name"), "current_task": state.get("current_task")})
def generate_true_false_node(state: ExamGenerationState) -> dict:
    return _generic_generate_question(state, "true_false")

@log_task(agent_name="generate_fill_in_blank", input_extractor=lambda state: {"unit_name": state.get("unit_name"), "current_task": state.get("current_task")})
def generate_fill_in_blank_node(state: ExamGenerationState) -> dict:
    return _generic_generate_question(state, "fill_in_blank")


@log_task(
    agent_name="refine_exam", 
    input_extractor=lambda state: {
        "unit_name": state.get("unit_name"),
        "critic_suggestions": state.get("critic_feedback", [])[-1].get("suggestions") if state.get("critic_feedback") else None,
        "feedback_count": len(state.get("critic_feedback", []))
    }

)
def refine_exam_node(state: ExamGenerationState) -> dict:
    """
    Refines the generated exam questions based on critic feedback.
    """
    critic_feedback = state.get("critic_feedback", [])
    if not critic_feedback:
        return {"error": "No feedback found for refinement."}
        
    latest_feedback = critic_feedback[-1]
    
    # We need to access the previous content.
    # In plan_generation_tasks_node, we cleared final_generated_content.
    # BUT we need it for refinement.
    # We should have preserved it or passed it in params.
    # The task params has 'feedback'.
    # Let's assume the state still has 'final_generated_content' because we are in a loop?
    # No, plan_generation_tasks_node returned "final_generated_content": [] to clear it.
    # This is a problem.
    # The planner should NOT clear it if it's a refinement task, OR it should pass it in params.
    # Let's assume for now we didn't clear it (I need to check plan_generation_tasks_node again).
    # In Step 262, I added "final_generated_content": [] to the return dict.
    # So it IS cleared.
    
    # I must fix plan_generation_tasks_node to NOT clear it if refining, 
    # OR pass it to the task.
    # Passing to task is safer.
    
    # But wait, I can't easily change plan_generation_tasks_node in this same tool call if I don't target it.
    # Let's assume I will fix plan_generation_tasks_node in the next step or use a workaround.
    # Workaround: The state passed to this node is the accumulated state.
    # If planner returned [], then state['final_generated_content'] is [].
    # So I MUST fix planner.
    
    # For now, let's implement the node assuming content is available in state or params.
    # I'll check state.get("final_generated_content") or params.
    
    current_task = state.get("current_task", {})
    params = current_task.get("params", {})
    
    # If content is empty, we are stuck.
    # Let's try to recover from history?
    # TeacherAgentState has 'final_generated_content'.
    # But we are in ExamGenerationState.
    # The TeacherAgent passes 'final_generated_content' down? No.
    
    # I will modify plan_generation_tasks_node to pass 'previous_content' in params.
    
    current_content = params.get("previous_content", state.get("final_generated_content", []))
    
    # Construct Prompt
    feedback_str = json.dumps(latest_feedback, ensure_ascii=False, indent=2)
    content_str = json.dumps(current_content, ensure_ascii=False, indent=2)
    
    system_prompt = prompt_manager.get_prompt("exam_generator.refine_system")
    
    user_prompt = prompt_manager.get_prompt(
        "exam_generator.refine_user",
        content_str=content_str,
        feedback_str=feedback_str
    )
    
    llm = get_llm()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    
    try:
        response = llm.invoke(messages)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        refined_content = json.loads(content)
        
        # Ensure it's a list
        if isinstance(refined_content, dict):
            if "questions" in refined_content and isinstance(refined_content["questions"], list):
                # Format: {"type": "...", "questions": [...]}
                refined_content = [refined_content]
            else:
                # Format: single question dict
                refined_content = [{"type": "multiple_choice", "questions": [refined_content]}]

        # Ensure all questions have globally unique numeric IDs based on seconds since epoch
        base_id = int(time.time())
        idx = 0
        for block in refined_content:
            if isinstance(block, dict) and "questions" in block:
                for q in block["questions"]:
                    if "id" not in q or not q["id"]:
                        q["id"] = base_id + idx
                        idx += 1
                    elif isinstance(q.get("id"), str) and q["id"].isdigit():
                        q["id"] = int(q["id"])
                    elif not isinstance(q.get("id"), int):
                        q["id"] = base_id + idx
                        idx += 1
             
        return {
            "final_generated_content": refined_content,
            "current_task": None # Task done
        }
    except Exception as e:
        return {"error": f"Refinement failed: {str(e)}"}

def handle_error_node(state: ExamGenerationState) -> ExamGenerationState:
    """Handles any errors that occurred during the process."""
    # This error is now logged at the node where it occurred.
    # This node is primarily for graph control flow.
    return state

def aggregate_final_output_node(state: ExamGenerationState) -> dict:
    """
    Aggregates all generated content and returns it in the state for the parent graph.
    """
    job_id = state['job_id']
    
    try:
        aggregated_output = []
        for content_item in state["final_generated_content"]:
            if isinstance(content_item, dict) and "type" in content_item and "questions" in content_item:
                aggregated_output.append(content_item)
            else:
                aggregated_output.append({"type": "unstructured_content", "content": content_item})

        if state.get("generation_errors"):
            aggregated_output.insert(0, {
                "type": "generation_warnings",
                "message": "Some question types failed to generate. Please check the details below.",
                "errors": state["generation_errors"]
            })
        
        # Determine final job status
        job_status = 'completed'
        if state.get("generation_errors"):
            job_status = 'partial_success' if len(aggregated_output) > 1 else 'failed'
        
        # db_logger.update_job_status(job_id, job_status, error_message="Some generation tasks failed." if job_status == 'partial_success' else None)

        existing_title = state.get("main_title")

        # Return the final aggregated content for the decorator to log and for the parent graph to use.
        return {
            "final_generated_content": aggregated_output,
            "main_title": existing_title if existing_title else f"未命名測驗 ({get_now_taipei().strftime('%Y-%m-%d')})",
            "retrieved_text_chunks": state.get("retrieved_text_chunks", []),  # ✅ 傳遞 RAG chunks 給 parent graph
            "parent_task_id": state.get("current_task_id")  # Propagate parent_task_id for proper task hierarchy
        }

    except Exception as e:
        error_message = f"Error aggregating final output: {str(e)}"
        db_logger.update_job_status(job_id, 'failed', error_message=error_message)
        # Return the error for the decorator to log
        return {"error": error_message, "generation_errors": state.get("generation_errors", []) + [{"task": "aggregate_final_output", "error_message": str(e)}]}