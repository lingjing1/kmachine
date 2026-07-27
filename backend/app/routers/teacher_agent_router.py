"""
Teacher Agent Router: 處理教師端 Agent 互動與 Critic 評估功能

此 router 包含：
1. Agent 對話互動 (chat_with_agent)
2. Critic 評估功能 (evaluate_by_job) - 因為 Critic 是 Agent 互動流程的一部分
"""
from typing import Any, List, Optional, Union
import json
import time
from fastapi import APIRouter, HTTPException, Depends
from backend.app.utils.auth_utils import get_current_user_id  # ✅ Phase 3: JWT 認證
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.app.agents.teacher_agent.graph import app as teacher_agent_app
from backend.app.utils import db_logger
from backend.app.utils.db_logger import engine, logger
from backend.app.utils.concurrency import run_in_db_pool
from sqlalchemy import text

# Create router
router = APIRouter(prefix="/api/v1", tags=["Teacher Agent Interaction"])

# --- Pydantic Models ---

# Critic workflow mapping
CRITIC_WORKFLOW_MAP = {
    1: [],                    # no_critic
    2: ["fact"],              # fact_only
    3: ["quality"],           # quality_only
    4: ["fact", "quality"]    # fact_then_quality
}

class ChatRequest(BaseModel):
    """Request model for chat with optional critic workflow."""
    source_ids: List[int] = Field(default_factory=list, description="List of unique content IDs to use as sources")
    generated_source_ids: List[int] = Field(default_factory=list, description="List of course content IDs for generated content sources")
    selected_kp_ids: List[str] = Field(default_factory=list, description="Selected KP mermaid IDs")
    selected_kp_names: List[str] = Field(default_factory=list, description="Selected KP names for context")
    unique_content_id: Optional[int] = Field(None, description="Deprecated: Use source_ids instead")
    prompt: str
    material_type: Optional[str] = Field(None, description="Material type: preview or review")
    length: Optional[str] = Field(None, description="Summary length: concise, standard, or detailed")
    question_types: Optional[List[str]] = Field(None, description="Exam question types: multiple_choice, true_false, etc.")
    question_count: Optional[int] = Field(None, description="Number of questions to generate")
    critic_workflow: int = Field(4, ge=1, le=4, description="1=no_critic,  2=fact_only, 3=quality_only, 4=fact_then_quality")
    mode: str = Field("quick", description="Evaluation mode: 'quick' or 'comprehensive'")
    max_iterations: int = Field(3, ge=1, le=5, description="Max refinement iterations")
    unit_id: Optional[int] = Field(None, description="Course unit ID for context")
    course_id: Optional[int] = Field(None, description="Course ID for context")
    model_name: Optional[str] = Field(None, description="Override LLM model for this request (e.g. gpt-4o, gpt-4o-mini)")
    ablation_group: Optional[str] = Field(None, description="Experimental group for ablation study (e.g., 'naive-rag', 'hybrid-rag', 'kp-hybrid-rag')")


class ChatResponse(BaseModel):
    job_id: int
    result: Any

class EvaluateRequest(BaseModel):
    """Request model for standalone evaluation."""
    job_id: int = Field(..., description="Job ID to evaluate")
    critic_workflow: int = Field(4, ge=2, le=4, description="2=fact_only, 3=quality_only, 4=fact_then_quality")
    mode: str = Field("quick", description="Evaluation mode: 'quick' or 'comprehensive'")

class ReferenceFeedbackRequest(BaseModel):
    chunk_id: Union[int, str]
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    error_types: List[str] = Field(default_factory=list)
    question_id: Optional[int] = Field(None, description="The specific question ID (if any)")

class RefineRequest(BaseModel):
    """Request model for manual refinement trigger."""
    # job_id is in URL
    max_iterations: int = Field(5, ge=1, le=10)
    force_refine: bool = Field(False, description="Allow refinement even if the latest evaluation passed")


# --- Agent Interaction Endpoint ---

# --- Job Status Endpoint ---

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: int):
    """
    Get the status and result of a generation job.
    Returns: {
        job_id, status, content, error, created_at
    }
    """
    from sqlalchemy import text
    from backend.app.utils.db_logger import engine



    def _sync_get_job_status(jid):
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    oj.id, oj.status, oj.created_at, oj.error_message,
                    gc.content, gc.title, gc.content_type, gc.id as content_id,
                    oj.input_config->'job_context' as job_context,
                    oj.total_iterations,
                    oj.input_config->>'original_prompt' as original_prompt
                FROM orchestration_jobs oj
                LEFT JOIN generated_contents gc ON oj.final_output_id = gc.id
                WHERE oj.id = :job_id
            """)
            row = conn.execute(query, {"job_id": jid}).fetchone()
            
            if not row:
                return None
            
            # job_context is at index 8, total_iterations is at index 9, original_prompt is at index 10
            job_context = row[8] or {}
            original_prompt = row[10]
            
            # Fetch current/latest task for step tracking
            latest_task_query = text("""
                SELECT agent_name FROM agent_tasks 
                WHERE job_id = :job_id 
                ORDER BY id DESC LIMIT 1
            """)
            latest_task_row = conn.execute(latest_task_query, {"job_id": jid}).fetchone()
            current_agent = latest_task_row[0] if latest_task_row else None
            
            # Map to descriptive name and avatar from metadata
            current_step_desc = "AI 正在努力思考中..."
            current_avatar = None
            if current_agent and current_agent in db_logger.AGENT_METADATA:
                agent_meta = db_logger.AGENT_METADATA[current_agent]
                current_step_desc = agent_meta.get("desc", current_step_desc)
                current_avatar = agent_meta.get("avatar")

            result = {
                "job_id": row[0],
                "status": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
                "error": row[3],
                "total_iterations": row[9] or 1,
                "prompt": original_prompt,
                "source_ids": job_context.get("source_ids", []),
                "generated_source_ids": job_context.get("generated_ids", []), # Note: in job_context it seems it was stored as generated_ids
                "selected_kp_ids": job_context.get("selected_kp_ids", []),
                "selected_kp_names": job_context.get("selected_kp_names", []),
                "unit_id": job_context.get("unit_id"),
                "material_type": job_context.get("material_type"),
                "length": job_context.get("length"),
                "question_types": job_context.get("question_types"),
                "question_count": job_context.get("question_count"),
                "current_agent": current_agent,
                "current_step_desc": current_step_desc,
                "current_avatar": current_avatar
            }

            
            if row[4]:  # If content exists
                result["content"] = {
                    "id": row[7],
                    "title": row[5],
                    "content_type": row[6],
                    "unit_id": job_context.get("unit_id"),
                    "content": row[4],
                    "display_type": row[4].get("display_type") if isinstance(row[4], dict) else None
                }
            return result

    result = await run_in_db_pool(_sync_get_job_status, job_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return result

@router.post("/jobs/{job_id}/refine", response_model=ChatResponse)
async def refine_job_content(
    job_id: int,
    request: RefineRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    Manually trigger a refinement iteration for an existing job.
    Uses the latest evaluation feedback from the database.
    """
    from backend.app.agents.teacher_agent.critics.critic_db_utils import (
        get_evaluations_by_job_id,
        get_generated_content_by_job_id
    )
    
    # 1. Get Job & Latest Evaluation
    evals = await run_in_db_pool(get_evaluations_by_job_id, job_id)
    if not evals:
        # If no evaluations found, we can't refine properly
        raise HTTPException(status_code=400, detail="Cannot refine: No evaluation history found for this job. Please run an evaluation first.")
    
    latest_eval = evals[0] # Ordered desc
    
    # 2. Check if refinement is needed
    if latest_eval.get("is_passed") and not request.force_refine:
        return ChatResponse(
            job_id=job_id,
            result={"status": "skipped", "message": "Content already passed evaluation. Use force_refine=true to override."}
        )

    # 3. Get Current Content
    content_data = await run_in_db_pool(get_generated_content_by_job_id, job_id)
    if not content_data:
        raise HTTPException(status_code=404, detail="Current generated content not found for this job.")

    # 4. Prepare state for graph
    # Extract original job info
    # We need full job_context to preserve original generation parameters (question types, count, etc.)
    
    with engine.connect() as conn:
        ctx_query = text("SELECT input_config, total_iterations FROM orchestration_jobs WHERE id = :jid")
        row = conn.execute(ctx_query, {"jid": job_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job record not found")
        
        input_config = row[0] or {}
        job_context = input_config.get("job_context", {})
        input_prompt = input_config.get("original_prompt", "Course Content Generation")
        total_iterations = row[1] or 1

    # Calculate target iteration for this refinement
    # If the job just finished initial generation, total_iterations is 1. 1st refinement is 2.
    next_iteration = total_iterations + 1

    # Map task type back to skill node
    display_type = content_data["content"].get("display_type") if isinstance(content_data["content"], dict) else content_data["content_type"]
    skill_map = {
        "exam_questions": "exam_generation_skill",
        "summary_report": "summarization_skill"
    }
    target_skill = skill_map.get(display_type, "exam_generation_skill")

    # Construct clean feedback summary for user_query (used for logging)
    feedback_data = latest_eval.get("feedback_for_generator", {})
    # Try all known feedback keys for a meaningful summary
    feedback_summary = (
        feedback_data.get("overall_feedback") or 
        feedback_data.get("improvement_suggestions") or 
        feedback_data.get("all_suggestions", ["Manual Refinement"])[0] if isinstance(feedback_data.get("all_suggestions"), list) else "Manual Refinement"
    )
    if isinstance(feedback_summary, list) and feedback_summary:
        feedback_summary = feedback_summary[0]
    
    refined_user_query = f"[Refinement] Job {job_id} | Eval {latest_eval.get('task_id')}: {str(feedback_summary)[:50]}..."

    # Create a parent task for this refinement session to provide proper hierarchy
    # This task represents the "refinement_orchestrator" agent that coordinates the skills
    refinement_orchestrator_task_id = await run_in_db_pool(
        db_logger.create_task,
        job_id=job_id,
        agent_name="refinement_orchestrator",
        task_input={"feedback": feedback_summary, "query": input_prompt, "unit_name": job_context.get("unit_name")},

        iteration_number=next_iteration
    )

    # Construct Critic Feedback in the format expected by the graph
    feedback_for_graph = {
        "iteration": total_iterations,
        "overall_status": "fail" if not latest_eval.get("is_passed") else "pass",
        "overall_passed": latest_eval.get("is_passed"),
        "feedback_items": latest_eval.get("feedback_for_generator", {}),
        "suggestions": latest_eval.get("feedback_for_generator", {}).get("all_suggestions", []),
        "timestamp": latest_eval.get("evaluated_at").isoformat() if latest_eval.get("evaluated_at") else None
    }

    # IMPORTANT: Ensure final_generated_content contains the actual content list/dict for the refinement prompt
    previous_content = content_data["content"].get("content") if isinstance(content_data["content"], dict) else content_data["content"]

    inputs = {
        "job_id": job_id,
        "user_id": user_id,
        "user_query": refined_user_query, # For log context
        "query": input_prompt,            # Original intent
        "source_ids": job_context.get("source_ids", []),
        "generated_source_ids": job_context.get("generated_source_ids", []),
        "selected_kp_names": job_context.get("selected_kp_names", []),
        "unit_name": job_context.get("unit_name"),
        "unit_id": job_context.get("unit_id"),
        "next_node": target_skill,
 
        "is_manual_refinement": True,
        "enabled_critics": [],     # Disable automatic loop
        
        # Proper iteration & hierarchy tracking
        "iteration_count": next_iteration,
        "parent_task_id": refinement_orchestrator_task_id, # Link all nodes under this
        
        # Preserve original generation settings
        "material_type": job_context.get("material_type"),
        "length": job_context.get("length"),
        "question_types": job_context.get("question_types"),
        "question_count": job_context.get("question_count"),
        
        # Populate feedback history
        "critic_feedback": [feedback_for_graph],
        "fact_feedback": latest_eval.get("feedback_for_generator", {}).get("fact_critic"),
        "quality_feedback": latest_eval.get("feedback_for_generator", {}).get("quality_critic"),
        "final_generated_content": previous_content,
        "max_iterations": next_iteration, # Just this one round
    }

    # 5. Execute in background
    import asyncio
    
    # Update job status and iteration count in DB immediately
    await run_in_db_pool(db_logger.update_job_status, job_id, 'running')
    
    from sqlalchemy import update
    from backend.app.utils.db_logger import orchestration_jobs
    with engine.connect() as conn:
        stmt = update(orchestration_jobs).where(orchestration_jobs.c.id == job_id).values(
            total_iterations=next_iteration
        )
        conn.execute(stmt)
        conn.commit()
    
    asyncio.create_task(_execute_graph(inputs, job_id))
    
    # Increment iteration count in DB immediately (or let the graph nodes handle it)
    # The graph nodes currently handle it, but we should ensure the next_iteration is clear.

    return ChatResponse(
        job_id=job_id,
        result={"status": "started", "message": f"Refinement iteration {total_iterations + 1} started."}
    )

# --- Agent Interaction Endpoints ---

class GenerateRequest(BaseModel):
    """Request model for simple generation (no critic)."""
    prompt: str
    source_ids: List[int] = Field(default_factory=list, description="List of unique content IDs to use as sources")
    generated_source_ids: List[int] = Field(default_factory=list, description="List of course content IDs for generated content sources")
    selected_kp_ids: List[str] = Field(default_factory=list, description="Selected KP mermaid IDs")
    selected_kp_names: List[str] = Field(default_factory=list, description="Selected KP names for context")
    material_type: Optional[str] = Field(None, description="Material type: preview or review")
    length: Optional[str] = Field(None, description="Summary length: concise, standard, or detailed")
    question_types: Optional[List[str]] = Field(None, description="Exam question types: multiple_choice, true_false, etc.")
    question_count: Optional[int] = Field(None, description="Number of questions to generate")
    unit_id: Optional[int] = Field(None, description="Course unit ID for context")
    course_id: Optional[int] = Field(None, description="Course ID for context")
    model_name: Optional[str] = Field(None, description="Override LLM model for this request (e.g. gpt-4o, gpt-4o-mini)")
    ablation_group: Optional[str] = Field(None, description="Experimental group for ablation study (e.g., 'naive-rag', 'hybrid-rag', 'kp-hybrid-rag')")

@router.post("/generate", response_model=ChatResponse)
async def generate_content(
    request: GenerateRequest,
    user_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 user_id
):
    """
    Simple generation endpoint (No Critic).
    Fast response, just content generation.
    """
    # Force critic_workflow=1 (no_critic)
    return await _run_agent_flow(
        prompt=request.prompt,
        user_id=user_id,
        source_ids=request.source_ids,
        generated_source_ids=request.generated_source_ids,
        selected_kp_ids=request.selected_kp_ids,
        selected_kp_names=request.selected_kp_names,
        material_type=request.material_type,
        length=request.length,
        question_types=request.question_types,
        question_count=request.question_count,
        critic_workflow=1,
        mode="quick",
        max_iterations=1,
        unit_id=request.unit_id,
        course_id=request.course_id,
        model_name=request.model_name,
        ablation_group=request.ablation_group
    )


@router.post("/generate/refined", response_model=ChatResponse)
async def generate_refined_content(
    request: ChatRequest,
    user_id: int = Depends(get_current_user_id)  # ✅ Phase 3: 從 JWT token 取得 user_id
):
    """
    Refined generation endpoint (With Critic & Iteration).
    
    critic_workflow options:
    - 2: fact_only (Faithfulness + TaskSatisfaction)
    - 3: quality_only (G-Eval)
    - 4: fact_then_quality (Fact must pass before Quality)
    """
    # Ensure critic_workflow is valid for refined (2-4), though 1 is technically handled by graph
    workflow = request.critic_workflow if request.critic_workflow > 1 else 4
    
    return await _run_agent_flow(
        prompt=request.prompt,
        user_id=user_id,
        source_ids=request.source_ids,
        generated_source_ids=request.generated_source_ids,
        selected_kp_ids=request.selected_kp_ids,
        selected_kp_names=request.selected_kp_names,
        material_type=request.material_type,
        length=request.length,
        question_types=request.question_types,
        question_count=request.question_count,
        critic_workflow=workflow,
        mode=request.mode,
        max_iterations=request.max_iterations,
        unit_id=request.unit_id,
        course_id=request.course_id,
        model_name=request.model_name,
        ablation_group=request.ablation_group
    )

async def _run_agent_flow(prompt, user_id, source_ids, generated_source_ids, selected_kp_ids, selected_kp_names, material_type, length, question_types, question_count, critic_workflow, mode, max_iterations, unit_id=None, course_id=None, model_name=None, ablation_group=None):
    """Internal helper to run the agent graph."""
    
    # Map workflow number to enabled_critics list
    enabled_critics = CRITIC_WORKFLOW_MAP.get(critic_workflow, [])
    
    # Determine workflow_type for DB logging
    workflow_type_map = {
        1: "1_no_critic",
        2: "2_fact_only", 
        3: "3_quality_only",
        4: "4_fact_then_quality"
    }
    workflow_type = workflow_type_map.get(critic_workflow, "agent_chat")
    
    # Resolve unit_name if unit_id is provided
    unit_name = None
    if unit_id:
        def _get_u_name():
            with engine.connect() as conn:
                res = conn.execute(text("SELECT name FROM course_units WHERE id = :id"), {"id": unit_id}).fetchone()
                return res[0] if res else None
        unit_name = await run_in_db_pool(_get_u_name)
        if not unit_name:
            unit_name = f"單元 {unit_id}"
        logger.info(f"🔍 Resolved unit_name for unit_id {unit_id}: {unit_name}")

    
    # Prepare job context

    job_context = {
        "source_ids": source_ids,
        "generated_ids": generated_source_ids,
        "selected_kp_ids": selected_kp_ids,
        "selected_kp_names": selected_kp_names,
        "unit_id": unit_id,
        "unit_name": unit_name,
        "course_id": course_id,
        "ablation_group": ablation_group
    }
    if material_type:
        job_context["material_type"] = material_type
    if length:
        job_context["length"] = length
    if question_types:
        job_context["question_types"] = question_types
    if question_count:
        job_context["question_count"] = question_count


    job_id = await run_in_db_pool(
        db_logger.create_job,
        user_id=user_id,
        input_prompt=prompt,
        workflow_type=workflow_type,
        job_context=job_context
    )
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to create a chat job.")

    # Auto-determine target skill if parameters are specific
    # This bypasses the LLM router which can occasionally misroute clear generation requests
    target_skill = None
    if material_type or length:
        target_skill = "summarization_skill"
    elif question_types or question_count:
        target_skill = "exam_generation_skill"

    # Input for the teacher_agent graph
    inputs = {
        "job_id": job_id,
        "user_id": user_id,
        "user_query": prompt,  # 使用原始 prompt
        "original_query": prompt,
        "source_ids": source_ids,
        "next_node": target_skill, # Bypass router if determined
        "generated_source_ids": generated_source_ids, # Pass generated IDs
        "selected_kp_ids": selected_kp_ids,
        "selected_kp_names": selected_kp_names,
        "unit_name": unit_name,
        "unit_id": unit_id,

        "unique_content_id": source_ids[0] if source_ids else 0,
        # Summary configuration
        "material_type": material_type,
        "length": length,
        # Critic configuration
        "enabled_critics": enabled_critics,
        "critic_mode": mode,
        "max_iterations": max_iterations,
        "model_name": model_name,
        "ablation_group": ablation_group,
    }

    # Start independent background task or await?
    # User plan says "Background execution, immediately return job_id"
    # BUT `teacher_agent_app.ainvoke` is currently awaited.
    # To support background execution properly, we should use BackgroundTasks
    # However, for now, to minimize architectural changes and since previously it was awaited,
    # I will modify the internal logic to run in background IF the framework supports it easily.
    # Given the complexity, I will keep `await` for now but note that this might block.
    # WAIT: User said "return job_id, background execution". 
    # If I await here, it won't return immediately.
    # I need to use FastAPI BackgroundTasks.
    
    # However, refactoring strictly to BackgroundTasks requires separating logic.
    # Let's use a background task wrapper.
    
    from fastapi import BackgroundTasks
    # But I need to change signature of `_run_agent_flow` or pass BackgroundTasks to endpoints.
    # Let's stick to Await for now (Simplest) OR BackgroundTasks if I can inject it.
    # Actually, the previous implementation AWAITED.
    # "Background execution" implies we shouldn't wait.
    # Let's check `teacher_agent_router.py` existing code. It was `await teacher_agent_app.ainvoke(inputs)`.
    # If I change to background, I need to make sure `db_logger` is updated.
    
    # Let's stick to `await` to ensure reliability for this iteration, 
    # unless user explicitly asked for non-blocking. 
    # User said "1. POST ... -> job_id, background execution".
    # This strongly suggests non-blocking.
    
    # I will use `run_in_threadpool` or just standard `asyncio.create_task`.
    import asyncio
    asyncio.create_task(_execute_graph(inputs, job_id))
    
    return ChatResponse(
        job_id=job_id,
        result={"status": "started", "message": "Job started in background"}
    )

async def _execute_graph(inputs, job_id):
    """Execute graph in background and handle errors."""
    try:
        # Update status to running as soon as we start
        await run_in_db_pool(db_logger.update_job_status, job_id, 'running')
        
        final_state = await teacher_agent_app.ainvoke(inputs)
        
        if final_state.get('error'):
             error_message = f"Generation failed: {final_state.get('error')}"
             await run_in_db_pool(db_logger.update_job_status, job_id, 'failed', error_message=error_message)
        else:
             # Success: Mark job as completed, which triggers metric aggregation
             await run_in_db_pool(db_logger.update_job_status, job_id, 'completed')
             
    except Exception as e:
        await run_in_db_pool(db_logger.update_job_status, job_id, 'failed', error_message=str(e))


# --- Standalone Evaluation Endpoint ---

@router.get("/jobs/{job_id}/evaluations")
async def get_job_evaluations(job_id: int):
    """
    Retrieve all evaluations for a specific job ID.
    Returns list derived from TASK_EVALUATIONS table.
    """
    from backend.app.agents.teacher_agent.critics.critic_db_utils import get_evaluations_by_job_id
    from backend.app.utils.db_logger import engine
    from sqlalchemy import text
    
    results = await run_in_db_pool(get_evaluations_by_job_id, job_id)
    
    # Fetch matching agent tasks to get duration
    agent_tasks_list = []
    try:
        def _sync_get_agent_tasks(jid):
            with engine.connect() as conn:
                at_query = text("""
                    SELECT id, duration_ms, created_at, agent_name 
                    FROM agent_tasks 
                    WHERE job_id = :job_id 
                    AND (agent_name LIKE '%critic%' OR agent_name = 'critic_agent')
                    ORDER BY created_at DESC
                """)
                return conn.execute(at_query, {"job_id": jid}).fetchall()

        agent_tasks_list = await run_in_db_pool(_sync_get_agent_tasks, job_id)
            
    except Exception as e:
        logger.error(f"Error fetching agent tasks: {e}")

    formatted_evals = []
    for i, row in enumerate(results):
        # Try to match with agent task for duration
        duration_ms = 0
        if i < len(agent_tasks_list):
            duration_ms = agent_tasks_list[i].duration_ms or 0
            
        feedback = row["feedback_for_generator"] or {}
        metrics = row["metric_details"] or {}
        
        # Determine format
        all_evals = metrics.get("all_evaluations") or feedback.get("all_evaluations")
        
        fact_critic = None
        quality_result = None
        
        if all_evals:
            # Unified format from graph.py (Legacy/Existing path)
            fact_evals = [e for e in all_evals if e.get("critic_type") == "fact" or e.get("criteria") in ["Faithfulness", "TaskSatisfaction"]]
            quality_evals = [e for e in all_evals if e.get("critic_type") == "quality" or (e.get("critic_type") is None and e.get("criteria") not in ["Faithfulness", "TaskSatisfaction"])]
            
            if fact_evals:
                faithfulness = next((e for e in fact_evals if e.get("criteria") == "Faithfulness"), {})
                satisfaction = next((e for e in fact_evals if e.get("criteria") == "TaskSatisfaction"), {})
                fact_critic = {
                    "passed": all(e.get("rating", 0) >= 4 for e in fact_evals),
                    "faithfulness": {
                        "score": faithfulness.get("rating", 0),
                        "analysis": faithfulness.get("analysis", ""),
                        "suggestions": faithfulness.get("suggestions", [])
                    },
                    "task_satisfaction": {
                        "score": satisfaction.get("rating", 0),
                        "analysis": satisfaction.get("analysis", ""),
                        "suggestions": satisfaction.get("suggestions", []),
                        "checks": satisfaction.get("checks", [])
                    }
                }
                
            if quality_evals:
                quality_result = {
                    "passed": all(e.get("rating", 0) >= 4 for e in quality_evals),
                    "evaluations": [
                        {
                            "rubric_name": e.get("criteria"),
                            "rating": e.get("rating", 0),
                            "analysis": e.get("analysis", ""),
                            "suggestions": e.get("suggestions", [])
                        } for e in quality_evals
                    ]
                }
            
        else:
            # Standalone/Manual trigger path (New async flow)
            # Row structure: feedback = {"overall_passed": ..., "fact_critic": ..., "quality_critic": ...}
            if row["evaluation_stage"] == 4:
                fact_critic = feedback.get("fact_critic")
                quality_result = feedback.get("quality_critic")
            elif row["evaluation_stage"] == 2:
                fact_critic = feedback
            elif row["evaluation_stage"] == 3:
                quality_result = feedback

        # Ensure consistent structure for quality evaluations
        if quality_result and "evaluations" in quality_result:
            # Ensure fields map to what CriticResultPanel expects
            processed_evals = []
            for e in quality_result["evaluations"]:
                processed_evals.append({
                    "rubric_name": e.get("rubric_name", e.get("criteria", "Unknown")),
                    "rating": e.get("rating", 0),
                    "analysis": e.get("analysis", e.get("feedback", "")),
                    "suggestions": e.get("suggestions", [])
                })
            quality_result["evaluations"] = processed_evals

        formatted_evals.append({
            "job_id": row["job_id"],
            "status": "completed",
            "critic_workflow": row["evaluation_stage"],
            "workflow_name": row["evaluation_mode"] or "unknown",
            "evaluation": {
                "overall_passed": row["is_passed"],
                "quality_critic": quality_result,
                "fact_critic": fact_critic
            },
            "duration_ms": duration_ms,
            "evaluated_at": row["evaluated_at"].isoformat() if row["evaluated_at"] else None
        })
        
    return {
        "job_id": job_id,
        "has_evaluations": len(results) > 0,
        "evaluations": formatted_evals
    }


@router.post("/evaluate")
async def evaluate_endpoint(request: EvaluateRequest):
    """
    Standalone evaluation endpoint for re-evaluating generated content.
    Runs in background to prevent timeouts.
    """
    import asyncio
    asyncio.create_task(_execute_standalone_evaluation(request))
    
    return {
        "job_id": request.job_id,
        "status": "started",
        "message": "Evaluation started in background"
    }

async def _execute_standalone_evaluation(request: EvaluateRequest):
    """Internal helper to run standalone evaluation in background."""
    import logging
    import time
    start_time = time.time()
    
    try:
        from backend.app.agents.teacher_agent.critics.quality_critic import QualityCritic
        from backend.app.agents.teacher_agent.critics.fact_critic import (
            CustomFaithfulness, get_fact_critic_llm
        )
        from backend.app.agents.teacher_agent.utils.llm_utils import get_llm
        from backend.app.agents.teacher_agent.critics.critic_db_utils import (
            get_generated_content_by_job_id,
            get_rag_chunks_by_job_id,
            save_agent_task_only,
            save_task_evaluation_record
        )
        
        # Map workflow to enabled critics
        enabled_critics = CRITIC_WORKFLOW_MAP.get(request.critic_workflow, ["fact", "quality"])
        
        # Step 1: Get generated content
        content_data = await run_in_db_pool(get_generated_content_by_job_id, request.job_id)
        if not content_data:
            logging.error(f"No content found for job_id {request.job_id}")
            return
        
        content = content_data["content"]
        content_type = content_data["content_type"]
        
        # Safely determine display_type
        if isinstance(content, dict):
            display_type = content.get("display_type", content_type)
        else:
            display_type = content_type
            
        # Step 2: Get RAG context
        rag_chunks = await run_in_db_pool(get_rag_chunks_by_job_id, request.job_id, 10)
        contexts = []
        if rag_chunks:
            contexts = [c['chunk_text'] for c in rag_chunks]
            
        # Prepare content for evaluation
        if isinstance(content, dict) and "content" in content:
            generated_content = content["content"]
        else:
            generated_content = content
            
        user_query = content_data.get("input_prompt", "")
        
        # Initialize results
        fact_result = None
        quality_result = None
        overall_passed = True
        total_flow_cost = 0.0
        total_flow_prompt_tokens = 0
        total_flow_completion_tokens = 0
        last_critic_task_id = None
        
        # Step 3: Run Fact Critic (if enabled)
        if "fact" in enabled_critics:
            logging.info(f"📐 Running Fact Critic for job {request.job_id}")
            fact_start = time.time()
            
            # Faithfulness
            faithfulness_metric = CustomFaithfulness(llm=get_fact_critic_llm())
            eval_data = {
                "user_input": user_query,
                "response": json.dumps(generated_content, ensure_ascii=False),
                "retrieved_contexts": contexts
            }
            faithfulness_res = await faithfulness_metric.score_with_feedback(eval_data)
            
            EVAL_THRESHOLD = 4
            fact_passed = (faithfulness_res["normalized_score"] >= EVAL_THRESHOLD)
            
            fact_result = {
                "passed": fact_passed,
                "faithfulness": {
                    "score": faithfulness_res["normalized_score"],
                    "raw_score": faithfulness_res["score"],
                    "analysis": faithfulness_res["analysis"],
                    "suggestions": faithfulness_res["suggestions"]
                }
            }
            
            # Log Fact Task
            fact_duration = int((time.time() - fact_start) * 1000)
            from backend.app.utils.db_logger import calculate_llm_cost, get_task_iteration_number
            target_task_id = content_data.get("source_agent_task_id")
            current_iter = await run_in_db_pool(get_task_iteration_number, target_task_id) if target_task_id else 1
            
            f_prompt_tokens = faithfulness_res.get("prompt_tokens", 0)
            f_completion_tokens = faithfulness_res.get("completion_tokens", 0)
            f_model = faithfulness_res.get("model_name") or "gpt-4o-mini"
            f_cost = calculate_llm_cost(f_model, f_prompt_tokens, f_completion_tokens)
            
            total_flow_cost += f_cost
            total_flow_prompt_tokens += f_prompt_tokens
            total_flow_completion_tokens += f_completion_tokens
            
            fact_task_id = await run_in_db_pool(
                save_agent_task_only,
                job_id=request.job_id,
                parent_task_id=target_task_id,
                agent_name="fact_critic",
                task_input={
                    "target_task_id": target_task_id,
                    "workflow": "fact_critic",
                    "mode": request.mode
                },
                output=fact_result,
                duration_ms=fact_duration,
                iteration_number=current_iter,
                prompt_tokens=f_prompt_tokens,
                completion_tokens=f_completion_tokens,
                model_name=f_model,
                estimated_cost_usd=f_cost
            )
            last_critic_task_id = fact_task_id
            
            # Skip intermediate save_task_evaluation_record for fact stage 
            # as it will be part of the final aggregated record.
            pass

            if not fact_passed:
                overall_passed = False
        
        # Step 4: Run Quality Critic (if enabled)
        should_run_quality = "quality" in enabled_critics
        
        if should_run_quality:
            logging.info(f"✨ Running Quality Critic for job {request.job_id}")
            quality_start = time.time()
            
            llm = get_llm()
            critic = QualityCritic(llm=llm, threshold=4.0)
            
            if display_type == "exam_questions":
                all_questions = []
                if isinstance(generated_content, list):
                    for block in generated_content:
                        questions = block.get("questions", [])
                        for q in questions:
                            q["question_type"] = block.get("type", "unknown")
                        all_questions.extend(questions)
                
                exam = {"type": "exam", "questions": all_questions}
                rag_text = "\n\n".join(contexts) if contexts else None
                
                evaluation = await critic.evaluate_exam(
                    exam=exam,
                    rag_content=rag_text,
                    mode=request.mode,
                    user_query=user_query
                )
                
                evaluations = evaluation.get("overall", {}).get("evaluations", [])
                quality_passed = all(e.get("rating", 0) >= 4.0 for e in evaluations)
                
            else:
                evaluation = await critic.evaluate(content=content, criteria=None, user_query=user_query)
                evaluations = evaluation.get("evaluations", [])
                quality_passed = all(e.get("rating", 0) >= 4.0 for e in evaluations)
            
            quality_result = {
                "passed": quality_passed,
                "evaluations": evaluations
            }
            
            quality_duration = int((time.time() - quality_start) * 1000)
            from backend.app.utils.db_logger import calculate_llm_cost, get_task_iteration_number
            target_task_id = content_data.get("source_agent_task_id")
            current_iter = await run_in_db_pool(get_task_iteration_number, target_task_id) if target_task_id else 1
            
            q_prompt_tokens = evaluation.get("prompt_tokens", 0)
            q_completion_tokens = evaluation.get("completion_tokens", 0)
            q_model = evaluation.get("model_name") or "gpt-4o-mini"
            q_cost = calculate_llm_cost(q_model, q_prompt_tokens, q_completion_tokens)
            
            total_flow_cost += q_cost
            total_flow_prompt_tokens += q_prompt_tokens
            total_flow_completion_tokens += q_completion_tokens
            
            quality_task_id = await run_in_db_pool(
                save_agent_task_only,
                job_id=request.job_id,
                parent_task_id=target_task_id,
                agent_name="quality_critic",
                task_input={
                    "target_task_id": target_task_id,
                    "workflow": "quality_critic",
                    "mode": request.mode
                },
                output=quality_result,
                duration_ms=quality_duration,
                iteration_number=current_iter,
                prompt_tokens=q_prompt_tokens,
                completion_tokens=q_completion_tokens,
                model_name=q_model,
                estimated_cost_usd=q_cost
            )
            last_critic_task_id = quality_task_id
            
            # Skip intermediate save_task_evaluation_record for quality stage
            # as it will be part of the final aggregated record.
            pass

            if not quality_passed:
                overall_passed = False
        
        # Step 5: Aggregated Evaluation Record
        workflow_names_map = {2: "fact_only", 3: "quality_only", 4: "fact_then_quality"}
        workflow_name = workflow_names_map.get(request.critic_workflow, "unknown")
        evaluation_mode = f"{workflow_name}_{request.mode}"
        
        current_stage = request.critic_workflow

        if not last_critic_task_id:
             target_task_id = content_data.get("source_agent_task_id")
             last_critic_task_id = target_task_id

        feedback_data = {
            "overall_passed": overall_passed,
            "all_suggestions": [],
            "fact_critic": fact_result,
            "quality_critic": quality_result
        }
        
        metrics_data = {
            "overall_passed": overall_passed,
            "scores": {
                "fact": {"faithfulness": fact_result["faithfulness"].get("score")} if fact_result else None,
                "quality": {e.get("rubric_name", e.get("criteria", "Unknown")): e.get("rating") for e in quality_result.get("evaluations", [])} if quality_result else None
            }
        }

        await run_in_db_pool(
            save_task_evaluation_record,
            task_id=last_critic_task_id,
            job_id=request.job_id,
            evaluation_stage=current_stage,
            evaluation_mode=evaluation_mode,
            is_passed=overall_passed,
            feedback=feedback_data,
            metrics_detail=metrics_data
        )
        
        from backend.app.utils.db_logger import update_job_iterations_and_cost
        await run_in_db_pool(update_job_iterations_and_cost, request.job_id)

        logging.info(f"✅ Standalone evaluation completed for job {request.job_id} in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Standalone evaluation failed: {e}")
        import traceback
        traceback.print_exc()


def _parse_quality_result_to_evaluations(quality_result):
    """
    Parse quality_result from metric_details into evaluations array.
    """
    if not quality_result:
        return []
    
    if "rubric_scores" in quality_result:
        return quality_result["rubric_scores"]
        
    if "evaluations" in quality_result:
        return quality_result["evaluations"]
    
    evaluations = []
    for key, value in quality_result.items():
        if isinstance(value, dict) and ("rating" in value or "score" in value):
            evaluations.append({
                "rubric_name": key,
                "rating": value.get("rating", value.get("score", 0)),
                "analysis": value.get("analysis", value.get("feedback", "")),
                "suggestions": value.get("suggestions", [])
            })
    
    return evaluations

def _parse_feedback_to_evaluations(feedback):
    if not feedback: return []
    if isinstance(feedback, list): return feedback
    if isinstance(feedback, dict) and "rubric_scores" in feedback:
        return feedback["rubric_scores"]
    return []


@router.post("/feedback/reference")
async def submit_reference_feedback(
    request: ReferenceFeedbackRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    Submit feedback for a specific reference chunk.
    """
    success = await run_in_db_pool(
        db_logger.save_reference_feedback,
        chunk_id=request.chunk_id,
        rating=request.rating,
        teacher_id=user_id,
        comment=request.comment,
        error_types=request.error_types,
        question_id=request.question_id
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save feedback.")
        
    return {"status": "success", "message": "Feedback received"}
