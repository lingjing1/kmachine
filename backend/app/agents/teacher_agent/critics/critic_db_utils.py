"""
Database utility functions for Quality Critic evaluation.
"""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, insert, update
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json
import logging

logger = logging.getLogger(__name__)

from backend.app.utils.db_logger import (
    engine, 
    orchestration_jobs, 
    generated_contents, 
    agent_tasks,
    agent_task_sources
)
from backend.app.utils.time_utils import get_now_taipei

# Reflect document_chunks table
from sqlalchemy import Table, MetaData
metadata = MetaData()
try:
    document_chunks = Table('document_chunks', metadata, autoload_with=engine)
    task_evaluations = Table('task_evaluations', metadata, autoload_with=engine)
except Exception as e:
    logger.warning(f"Could not reflect tables: {e}")
    document_chunks = None
    task_evaluations = None


def get_generated_content_by_job_id(job_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve generated content and metadata by job_id.
    
    Returns:
        Dict containing:
        - content_id: int
        - content_type: str
        - content: dict
        - title: str
        - created_at: datetime
        - source_agent_task_id: int
        - user_id: int
        - input_prompt: str
    """
    try:
        with engine.connect() as conn:
            # Step 1: Get final_output_id from orchestration_jobs
            job_stmt = select(
                orchestration_jobs.c.final_output_id,
                orchestration_jobs.c.user_id,
                orchestration_jobs.c.input_config,
                orchestration_jobs.c.status
            ).where(orchestration_jobs.c.id == job_id)
            
            job_result = conn.execute(job_stmt).fetchone()
            
            if not job_result:
                logger.info(f"Job {job_id} not found")
                return None
            
            if job_result.status != 'completed':
                logger.info(f"Job {job_id} not completed (status: {job_result.status})")
                return None
            
            if not job_result.final_output_id:
                logger.info(f"Job {job_id} has no final_output_id")
                return None
            
            # Extract input_prompt from input_config
            input_prompt = ""
            if job_result.input_config:
                base_prompt = job_result.input_config.get("original_prompt", "")
                kps = job_result.input_config.get("knowledge_points", job_result.input_config.get("knowledge_concepts", None))
                
                parts = []
                if base_prompt:
                    parts.append(f"教師自訂指令：\n{base_prompt}")
                if kps:
                    parts.append(f"目標知識點 (Knowledge Points)：\n{kps}")
                    
                input_prompt = "\n\n".join(parts)
            
            # Step 2: Get generated content
            content_stmt = select(
                generated_contents.c.id,
                generated_contents.c.content_type,
                generated_contents.c.content,
                generated_contents.c.title,
                generated_contents.c.created_at,
                generated_contents.c.source_agent_task_id
            ).where(generated_contents.c.id == job_result.final_output_id)
            
            content_result = conn.execute(content_stmt).fetchone()
            
            if not content_result:
                logger.info(f"Content {job_result.final_output_id} not found")
                return None
            
            # Step 3: Check if there's an updated version in course_contents
            from sqlalchemy import text
            course_stmt = text(
                "SELECT content, title, created_at FROM course_contents WHERE source_id = :content_id ORDER BY id DESC LIMIT 1"
            )
            course_result = conn.execute(course_stmt, {"content_id": content_result.id}).fetchone()
            
            final_content = content_result.content
            final_title = content_result.title
            final_created_at = content_result.created_at
            
            if course_result and course_result.content:
                final_content = course_result.content
                if hasattr(course_result, 'title') and course_result.title:
                    final_title = course_result.title
                if hasattr(course_result, 'created_at') and course_result.created_at:
                    final_created_at = course_result.created_at
            
            return {
                "content_id": content_result.id,
                "content_type": content_result.content_type,
                "content": final_content,
                "title": final_title,
                "created_at": final_created_at,
                "source_agent_task_id": content_result.source_agent_task_id,
                "user_id": job_result.user_id,
                "input_prompt": input_prompt
            }
            
    except Exception as e:
        logger.error(f"ERROR retrieving content for job {job_id}: {e}")
        return None


def get_rag_chunks_by_task_id(task_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve RAG chunks referenced by an agent task.
    
    Args:
        task_id: Agent task ID
        limit: Maximum number of chunks to retrieve
    
    Returns:
        List of dicts containing:
        - chunk_id: int
        - chunk_text: str
        - metadata: dict (contains page_number, etc.)
    """
    if document_chunks is None:
        logger.warning("document_chunks table not available")
        return []
    
    try:
        with engine.connect() as conn:
            # Import and_ for proper SQL and condition
            from sqlalchemy import and_
            
            # Join agent_task_sources with document_chunks
            stmt = select(
                document_chunks.c.id,
                document_chunks.c.chunk_text,
                document_chunks.c.metadata,
                document_chunks.c.chunk_order
            ).select_from(
                agent_task_sources.join(
                    document_chunks,
                    and_(
                        agent_task_sources.c.source_id == document_chunks.c.id,
                        agent_task_sources.c.source_type.in_(['chunk', 'document_chunk'])
                    )
                )
            ).where(
                agent_task_sources.c.task_id == task_id
            ).order_by(
                document_chunks.c.chunk_order
            ).limit(limit)
            
            results = conn.execute(stmt).fetchall()
            
            chunks = [
                {
                    "chunk_id": row.id,
                    "chunk_text": row.chunk_text,
                    "metadata": row.metadata if row.metadata else {}
                }
                for row in results
            ]
            
            logger.info(f"Retrieved {len(chunks)} chunks for task {task_id}")
            return chunks
            
    except Exception as e:
        logger.error(f"ERROR retrieving chunks for task {task_id}: {e}")
        return []


def get_rag_chunks_by_job_id(job_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve RAG chunks for a job by looking up 'retriever' agent tasks.
    
    Args:
        job_id: Orchestration Job ID
        limit: Maximum number of chunks to retrieve
    
    Returns:
        List of dicts containing:
        - chunk_id: int
        - chunk_text: str
        - metadata: dict
    """
    if document_chunks is None:
        logger.warning("document_chunks table not available")
        return []
    
    try:
        with engine.connect() as conn:
            # Import and_ for proper SQL and condition
            from sqlalchemy import and_
            
            # Strategy:
            # 1. Find tasks for this job where agent_name = 'retriever'
            # 2. Join with agent_task_sources and document_chunks
            
            stmt = select(
                document_chunks.c.id,
                document_chunks.c.chunk_text,
                document_chunks.c.metadata,
                document_chunks.c.chunk_order
            ).select_from(
                agent_tasks.join(
                    agent_task_sources,
                    agent_tasks.c.id == agent_task_sources.c.task_id
                ).join(
                    document_chunks,
                    and_(
                        agent_task_sources.c.source_id == document_chunks.c.id,
                        agent_task_sources.c.source_type.in_(['chunk', 'document_chunk'])
                    )
                )
            ).where(
                and_(
                    agent_tasks.c.job_id == job_id,
                    agent_tasks.c.agent_name == 'retriever'  # Target the retriever agent
                )
            ).order_by(
                document_chunks.c.chunk_order
            ).limit(limit)
            
            results = conn.execute(stmt).fetchall()
            
            chunks = [
                {
                    "chunk_id": row.id,
                    "chunk_text": row.chunk_text,
                    "metadata": row.metadata if row.metadata else {}
                }
                for row in results
            ]
            
            logger.info(f"Retrieved {len(chunks)} chunks for job {job_id} (via retriever tasks)")
            return chunks
            
    except Exception as e:
        logger.error(f"ERROR retrieving chunks for job {job_id}: {e}")
        import traceback
        traceback.print_exc()
        return []




def save_critic_evaluation_to_db(
    task_id: int,  # Use existing critic node's task_id
    job_id: int,
    evaluation_stage: int,  # 1=fact, 2=quality
    evaluation_result: Dict[str, Any],
    is_passed: bool,
    feedback: Dict[str, Any],
    metrics_detail: Dict[str, Any],
    duration_ms: int,
    evaluation_mode: str,
    iteration_number: int
) -> Optional[int]:
    """
    Save critic evaluation to TASK_EVALUATIONS table only.
    
    Does NOT create a separate agent_task. Instead, references the existing
    critic node's task_id (from @log_task decorator).
    
    Args:
        task_id: ID of the critic node's task (fact_critic or quality_critic)
        job_id: Original orchestration job ID
        evaluation_stage: 1=fact, 2=quality
        evaluation_result: Full evaluation results dict
        is_passed: Whether evaluation passed
        feedback: Structured feedback dict
        metrics_detail: Metrics dict for experiments
        duration_ms: Evaluation duration in milliseconds
        evaluation_mode: Evaluation mode (exam_quick, exam_comprehensive, etc.)
        iteration_number: Current iteration number
    
    Returns:
        task_evaluation_id if successful, None otherwise
    """
    if task_evaluations is None:
        logger.warning("task_evaluations table not available")
        return None
    
    try:
        with engine.connect() as conn:
            # Create TASK_EVALUATIONS record only
            eval_stmt = insert(task_evaluations).values(
                task_id=task_id,  # Reference existing critic node's task
                job_id=job_id,
                evaluation_stage=evaluation_stage,
                evaluation_mode=evaluation_mode,
                is_passed=is_passed,
                feedback_for_generator=feedback,
                metric_details=metrics_detail,
                evaluated_at=get_now_taipei()
            ).returning(task_evaluations.c.id)
            
            eval_result = conn.execute(eval_stmt)
            task_evaluation_id = eval_result.scalar_one()
            
            conn.commit()
            
            logger.info(f"Saved evaluation: task_id={task_id}, eval_id={task_evaluation_id}, stage={evaluation_stage}")
            return task_evaluation_id
            
    except Exception as e:
        logger.error(f"ERROR saving evaluation for task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        return None



def save_agent_task_only(
    job_id: int,
    parent_task_id: int,
    agent_name: str,
    task_input: Dict[str, Any],
    output: Dict[str, Any],
    duration_ms: int,
    iteration_number: int = 1,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model_name: Optional[str] = None,
    estimated_cost_usd: float = 0.0
) -> Optional[int]:
    """Saves a task record to agent_tasks without creating an evaluation record."""
    try:
        with engine.connect() as conn:
            stmt = insert(agent_tasks).values(
                job_id=job_id,
                parent_task_id=parent_task_id,
                iteration_number=iteration_number,
                agent_name=agent_name,
                task_input=task_input,
                output=output,
                status='completed',
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model_name=model_name,
                estimated_cost_usd=estimated_cost_usd,
                created_at=get_now_taipei(),
                completed_at=get_now_taipei()
            ).returning(agent_tasks.c.id)
            
            result = conn.execute(stmt)
            task_id = result.scalar_one()
            conn.commit()
            return task_id
    except Exception as e:
        logger.error(f"Failed to save agent task {agent_name}: {e}")
        return None

def save_task_evaluation_record(
    task_id: int,
    job_id: int,
    evaluation_stage: int,
    evaluation_mode: str,
    is_passed: bool,
    feedback: Dict[str, Any],
    metrics_detail: Dict[str, Any]
) -> Optional[int]:
    """Saves ONLY the record in task_evaluations table linked to an existing task_id."""
    if task_evaluations is None:
        return None
    try:
        with engine.connect() as conn:
            eval_stmt = insert(task_evaluations).values(
                task_id=task_id,
                job_id=job_id,
                evaluation_stage=evaluation_stage,
                evaluation_mode=evaluation_mode,
                is_passed=is_passed,
                feedback_for_generator=feedback,
                metric_details=metrics_detail,
                evaluated_at=get_now_taipei()
            ).returning(task_evaluations.c.id)
            
            eval_result = conn.execute(eval_stmt)
            task_evaluation_id = eval_result.scalar_one()
            conn.commit()
            return task_evaluation_id
    except Exception as e:
        logger.error(f"Failed to save task evaluation record: {e}")
        return None

def save_evaluation_to_db(
    job_id: int,
    parent_task_id: int,
    evaluation_result: Dict[str, Any],
    duration_ms: int,
    is_passed: bool,
    feedback: Dict[str, Any],
    metrics_detail: Dict[str, Any] = None,
    evaluation_mode: str = "exam_comprehensive",
    evaluation_stage: int = 1,
    iteration_number: int = 1,
    task_input: Optional[Dict[str, Any]] = None,
    agent_name: str = "quality_critic",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model_name: Optional[str] = None,
    estimated_cost_usd: float = 0.0
) -> Optional[Tuple[int, int]]:
    """
    Save evaluation results to AGENT_TASKS and TASK_EVALUATIONS tables.
    
    Creates a new AGENT_TASK for the evaluation and a TASK_EVALUATIONS record.
    """
    if task_evaluations is None:
        logger.warning("task_evaluations table not available")
        return None
    
    try:
        with engine.connect() as conn:
            # Step 1: Create AGENT_TASK for evaluation
            task_stmt = insert(agent_tasks).values(
                job_id=job_id,
                parent_task_id=parent_task_id,
                iteration_number=iteration_number,
                agent_name=agent_name,
                task_input=task_input or {
                    "job_id": job_id, 
                    "parent_task_id": parent_task_id,
                    "evaluation_type": "manual_trigger"
                },
                output=evaluation_result,
                status='completed',
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model_name=model_name,
                estimated_cost_usd=estimated_cost_usd,
                created_at=get_now_taipei(),
                completed_at=get_now_taipei()
            ).returning(agent_tasks.c.id)
            
            task_result = conn.execute(task_stmt)
            evaluation_task_id = task_result.scalar_one()
            conn.commit() # Commit task first

            # Step 2: Create TASK_EVALUATIONS record using helper
            task_evaluation_id = save_task_evaluation_record(
                task_id=evaluation_task_id,
                job_id=job_id,
                evaluation_stage=evaluation_stage,
                evaluation_mode=evaluation_mode,
                is_passed=is_passed,
                feedback=feedback,
                metrics_detail=metrics_detail
            )
            
            if not task_evaluation_id:
                return None
                
            logger.info(f"Saved evaluation: task_id={evaluation_task_id}, eval_id={task_evaluation_id}")
            return (evaluation_task_id, task_evaluation_id)
            
    except Exception as e:
        logger.error(f"ERROR saving evaluation for job {job_id}: {e}")
        return None

def get_evaluations_by_job_id(job_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all evaluations for a specific job, ordered by time (newest first).
    """
    if task_evaluations is None:
        logger.warning("task_evaluations table not available")
        return []
        
    try:
        with engine.connect() as conn:
            stmt = select(
                task_evaluations.c.id,
                task_evaluations.c.task_id,
                task_evaluations.c.job_id,
                task_evaluations.c.evaluation_stage,
                task_evaluations.c.evaluation_mode,
                task_evaluations.c.is_passed,
                task_evaluations.c.feedback_for_generator,
                task_evaluations.c.metric_details,
                task_evaluations.c.evaluated_at
            ).where(
                task_evaluations.c.job_id == job_id
            ).order_by(
                task_evaluations.c.evaluated_at.desc()
            )
            
            results = conn.execute(stmt).fetchall()
            
            return [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "job_id": row.job_id,
                    "evaluation_stage": row.evaluation_stage,
                    "evaluation_mode": row.evaluation_mode,
                    "is_passed": row.is_passed,
                    "feedback_for_generator": row.feedback_for_generator,
                    "metric_details": row.metric_details,
                    "evaluated_at": row.evaluated_at
                }
                for row in results
            ]
            
    except Exception as e:
        logger.error(f"ERROR retrieving evaluations for job {job_id}: {e}")
        return []
