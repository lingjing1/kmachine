import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.utils.db_logger import engine
from backend.app.utils.concurrency import run_in_db_pool
from backend.app.utils.auth_utils import get_current_user_id
import json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Teacher - Experiment"])

class EvaluationResponse(BaseModel):
    id: int
    exp_generated_content_id: int
    human_fact_score: Optional[int]
    human_quality_scores: Optional[Dict[str, Any]]
    llm_agreement_status: Optional[str]
    llm_agreement_feedback: Optional[str]

class ExperimentContentResponse(BaseModel):
    id: int
    course_name: str
    ablation_group: str
    content_type: str
    content: Dict[str, Any]
    rag_metrics: Dict[str, Any]
    critic_scores: Dict[str, Any]
    evaluation: Optional[EvaluationResponse] = None
    input_config: Optional[dict] = None

class EvalSubmitRequest(BaseModel):
    exp_generated_content_id: int
    human_fact_score: int
    human_quality_scores: Dict[str, Any]

class EvalFeedbackRequest(BaseModel):
    evaluation_id: int
    llm_agreement_status: str
    llm_agreement_feedback: Optional[str] = None


def _sync_get_evaluations(reviewer_id: int):
    with engine.connect() as conn:
        # Fetch up to 20 selected contents
        query = text("""
            SELECT e.id, e.course_name, e.ablation_group, e.content_type, e.content, e.rag_metrics, e.critic_scores,
                   h.id as eval_id, h.human_fact_score, h.human_quality_scores, h.llm_agreement_status, h.llm_agreement_feedback,
                   s.input_config, cu.name
            FROM exp_generated_contents e
            LEFT JOIN exp_human_evaluations h ON h.exp_generated_content_id = e.id AND h.reviewer_id = :reviewer_id
            LEFT JOIN exp_seed_configs s ON e.seed_config_id = s.id
            LEFT JOIN course_units cu ON cu.id = CAST((s.input_config::jsonb)->>'unit_id' AS INTEGER)
            WHERE e.is_selected_for_eval = TRUE
            ORDER BY e.created_at DESC, e.id ASC
            LIMIT 20
        """)
        result = conn.execute(query, {"reviewer_id": reviewer_id})
        
        contents = []
        for row in result:
            content_json = row[4] if isinstance(row[4], dict) else json.loads(row[4] or '{}')
            rag_metrics = row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{}')
            critic_scores = row[6] if isinstance(row[6], dict) else json.loads(row[6] or '{}')
            
            evaluation = None
            if row[7] is not None:
                eval_quality_scores = row[9] if isinstance(row[9], dict) else json.loads(row[9] or '{}')
                evaluation = EvaluationResponse(
                    id=row[7],
                    exp_generated_content_id=row[0],
                    human_fact_score=row[8],
                    human_quality_scores=eval_quality_scores,
                    llm_agreement_status=row[10],
                    llm_agreement_feedback=row[11]
                )
            
            input_config = row[12] if isinstance(row[12], dict) else json.loads(row[12] or '{}')
            unit_name = row[13]
            if unit_name:
                input_config["unit_name"] = unit_name
            
            contents.append(ExperimentContentResponse(
                id=row[0],
                course_name=row[1] or 'Unknown',
                ablation_group=row[2],
                content_type=row[3],
                content=content_json,
                rag_metrics=rag_metrics,
                critic_scores=critic_scores,
                evaluation=evaluation,
                input_config=input_config
            ))
        return contents

@router.get("/api/teacher/experiment/evaluations", response_model=List[ExperimentContentResponse])
async def get_experiment_evaluations(current_user_id: int = Depends(get_current_user_id)):
    """Fetch generated contents selected for human evaluation."""
    contents = await run_in_db_pool(_sync_get_evaluations, current_user_id)
    return contents


def _sync_submit_evaluation(reviewer_id: int, reviewer_name: str, req: dict):
    with engine.connect() as conn:
        # Check if already exists
        check_q = text("SELECT id FROM exp_human_evaluations WHERE exp_generated_content_id = :content_id AND reviewer_id = :reviewer_id")
        existing = conn.execute(check_q, {"content_id": req['exp_generated_content_id'], "reviewer_id": reviewer_id}).fetchone()
        
        if existing:
            # Update existing Phase 1 scores
            update_q = text("""
                UPDATE exp_human_evaluations
                SET human_fact_score = :fact_score, human_quality_scores = :quality_scores, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                RETURNING id
            """)
            result = conn.execute(update_q, {
                "fact_score": req['human_fact_score'],
                "quality_scores": json.dumps(req['human_quality_scores']),
                "id": existing[0]
            })
            eval_id = result.fetchone()[0]
        else:
            # Insert new Evaluation
            insert_q = text("""
                INSERT INTO exp_human_evaluations 
                (exp_generated_content_id, reviewer_id, reviewer_name, human_fact_score, human_quality_scores)
                VALUES (:content_id, :reviewer_id, :reviewer_name, :fact_score, :quality_scores)
                RETURNING id
            """)
            result = conn.execute(insert_q, {
                "content_id": req['exp_generated_content_id'],
                "reviewer_id": reviewer_id,
                "reviewer_name": reviewer_name,
                "fact_score": req['human_fact_score'],
                "quality_scores": json.dumps(req['human_quality_scores'])
            })
            eval_id = result.fetchone()[0]
            
        conn.commit()
        return eval_id

@router.post("/api/teacher/experiment/evaluations/submit")
async def submit_evaluation(req: EvalSubmitRequest, current_user_id: int = Depends(get_current_user_id)):
    """Phase 1: Submit blind human rating scores."""
    # Assuming reviewer_name is fetched somewhere or can be derived. 
    # For now, we fetch it inside DB sync or pass empty string. We'll refine if needed.
    reviewer_name = f"Teacher_{current_user_id}" 
    
    # Let's fetch the actual name inside sync method to be precise.
    def db_logic(_uid, _req):
        with engine.connect() as conn:
            user_row = conn.execute(text("SELECT full_name FROM users WHERE id = :id"), {"id": _uid}).fetchone()
            name = user_row[0] if user_row else f"Teacher_{_uid}"
        return _sync_submit_evaluation(_uid, name, _req)

    eval_id = await run_in_db_pool(db_logic, current_user_id, req.dict())
    return {"message": "Evaluation scores saved successfully.", "evaluation_id": eval_id}


def _sync_submit_feedback(reviewer_id: int, req: dict):
    with engine.connect() as conn:
        update_q = text("""
            UPDATE exp_human_evaluations
            SET llm_agreement_status = :status, llm_agreement_feedback = :feedback, updated_at = CURRENT_TIMESTAMP
            WHERE id = :eval_id AND reviewer_id = :reviewer_id
            RETURNING id
        """)
        result = conn.execute(update_q, {
            "status": req['llm_agreement_status'],
            "feedback": req['llm_agreement_feedback'],
            "eval_id": req['evaluation_id'],
            "reviewer_id": reviewer_id
        }).fetchone()
        
        conn.commit()
        return result is not None

@router.post("/api/teacher/experiment/evaluations/feedback")
async def submit_evaluation_feedback(req: EvalFeedbackRequest, current_user_id: int = Depends(get_current_user_id)):
    """Phase 2: Submit agreement status and feedback to LLM Critic."""
    success = await run_in_db_pool(_sync_submit_feedback, current_user_id, req.dict())
    if not success:
        raise HTTPException(status_code=404, detail="Evaluation not found or unauthorized.")
    return {"message": "Feedback saved successfully."}
