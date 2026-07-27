import asyncio
import json
import logging
import uuid
import sys
import os
from sqlalchemy import create_engine, text

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(repo_root, "backend"))

from app.utils.db_logger import engine, create_job
from app.agents.teacher_agent.graph import app as teacher_agent_app
from app.agents.teacher_agent.critics.critic_db_utils import get_rag_chunks_by_job_id
from app.agents.teacher_agent.critics.fact_critic import CustomFaithfulness, get_fact_critic_llm
from app.agents.teacher_agent.critics.quality_critic import QualityCritic
from app.agents.teacher_agent.utils.llm_utils import get_llm


class _ExperimentContextFilter(logging.Filter):
    """
    Injects the current experiment context (seed_id, ablation_group) into
    every log record so that [COOK-AI] lines are traceable.
    """
    def __init__(self):
        super().__init__()
        self.seed_id: str = "?"
        self.group: str = "?"

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = f"[seed={self.seed_id} | {self.group}] {record.msg}"
        return True


_exp_filter = _ExperimentContextFilter()


def _set_exp_context(seed_id, group: str):
    _exp_filter.seed_id = seed_id
    _exp_filter.group = group


def _clear_exp_context():
    _exp_filter.seed_id = "?"
    _exp_filter.group = "?"


def _attach_filter():
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(_exp_filter)

async def run_all():
    _attach_filter()
    run_id = str(uuid.uuid4())
    seeds = []
    with engine.connect() as conn:
        res = conn.execute(text("SELECT id, input_config, course_name, unit_id FROM exp_seed_configs")).fetchall()
        for r in res:
            seeds.append({
                "id": r[0],
                "input_config": r[1] if isinstance(r[1], dict) else json.loads(r[1]),
                "course_name": r[2],
                "unit_id": r[3]
            })
            
    if not seeds:
        print("No seeds found.")
        return
        
    for seed in seeds:
        seed_id = seed["id"]
        config = seed["input_config"]
        unit_id = seed["unit_id"]
        
        groups = ["naive-rag", "hybrid-rag", "kp-hybrid-rag"]
        print(f"=== Starting Run for Seed {seed_id} ===")
        
        for group in groups:
            print(f"--- Running {group} ---")
            _set_exp_context(seed_id, group)
            current_config = config.copy()
            
            job_context = {
                "source_ids": current_config.get("source_ids", []),
                "generated_ids": current_config.get("generated_source_ids", []),
                "selected_kp_ids": current_config.get("selected_kp_ids", []),
                "selected_kp_names": current_config.get("selected_kp_names", []),
                "ablation_group": group
            }
            user_id = current_config.get("user_id", 1)
            job_id = create_job(
                user_id=user_id,
                input_prompt=current_config.get("prompt", ""),
                workflow_type="1_no_critic",
                job_context=job_context
            )
            
            target_skill = "exam_generation_skill" if current_config.get("content_type") == "exam" else "summarization_skill"
            
            inputs = {
                "job_id": job_id,
                "user_id": user_id,
                "user_query": current_config.get("prompt", ""),
                "original_query": current_config.get("prompt", ""),
                "source_ids": current_config.get("source_ids", []),
                "next_node": target_skill,
                "generated_source_ids": current_config.get("generated_source_ids", []),
                "selected_kp_ids": current_config.get("selected_kp_ids", []),
                "selected_kp_names": current_config.get("selected_kp_names", []),
                "unit_id": unit_id,
                "material_type": current_config.get("material_type"),
                "length": current_config.get("length"),
                "enabled_critics": [],
                "critic_mode": "quick",
                "max_iterations": 1,
                "model_name": current_config.get("model_name", "gpt-4o-mini"),
                "ablation_group": group,
            }
            
            try:
                final_state = await teacher_agent_app.ainvoke(inputs)
                content = final_state.get("final_generated_content")
                if content:
                    print(f"[{group}] Generation successful.")
                    
                    # 1. RAG Metrics
                    rag_metrics = {}
                    with engine.connect() as conn:
                        res = conn.execute(text("SELECT output FROM agent_tasks WHERE job_id=:j AND agent_name='retriever' ORDER BY id DESC LIMIT 1"), {"j": job_id}).fetchone()
                        if res and res[0]:
                            out_val = res[0]
                            if isinstance(out_val, str):
                                try:
                                    out_val = json.loads(out_val)
                                except Exception:
                                    out_val = {}
                            rag_metrics = out_val.get("rag_metrics", {}) if isinstance(out_val, dict) else {}
                    
                    # 2. Critic Evaluation
                    critic_scores = {}
                    generated_text = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
                    
                    chunks = get_rag_chunks_by_job_id(job_id)
                    context_strs = [c["chunk_text"] for c in chunks]
                    context_str_combined = "\n".join(context_strs)
                    
                    print(f"[{group}] Evaluating Fact Critic...")
                    fact_llm = get_fact_critic_llm()
                    fact_critic = CustomFaithfulness()
                    fact_critic.llm = fact_llm
                    fact_row = {
                        "user_input": current_config.get("prompt", ""),
                        "response": generated_text,
                        "retrieved_contexts": context_strs
                    }
                    fact_res = await fact_critic.score_with_feedback(fact_row)
                    raw_score = fact_res.get("score", 0)
                    critic_scores["fact_critic"] = {
                        "passed": fact_res.get("normalized_score", int(round(1.0 + (raw_score * 4.0)))) >= 4,
                        "faithfulness": {
                            "score": fact_res.get("normalized_score", int(round(1.0 + (raw_score * 4.0)))),
                            "analysis": fact_res.get("analysis", ""),
                            "raw_score": raw_score,
                            "suggestions": fact_res.get("suggestions", [])
                        }
                    }
                    
                    print(f"[{group}] Evaluating Quality Critic...")
                    from langchain_openai import ChatOpenAI
                    quality_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                    quality_critic = QualityCritic(llm=quality_llm)
                    if current_config.get("content_type") == "exam":
                        all_questions = []
                        if isinstance(content, list):
                            for block in content:
                                questions = block.get("questions", [])
                                for q in questions:
                                    q["question_type"] = block.get("type", "unknown")
                                all_questions.extend(questions)
                        exam_data = {"type": "exam", "questions": all_questions}
                        q_obj = await quality_critic.evaluate_exam(
                            exam=exam_data,
                            rag_content=context_str_combined, 
                            mode="quick", 
                            user_query=current_config.get("prompt", "")
                        )
                        q_res = q_obj.get("overall", {})
                    else:
                        q_res = await quality_critic.evaluate(
                            content=content,
                            user_query=current_config.get("prompt", "")
                        )
                    critic_scores["quality_details"] = q_res.get("evaluations", [])
                    s = [e.get("rating", 0) for e in q_res.get("evaluations", [])]
                    critic_scores["quality_avg"] = sum(s)/len(s) if s else 0
                    
                    # Insert into DB
                    with engine.begin() as conn:
                        job_row = conn.execute(
                            text("SELECT total_cost_usd, total_cost_twd, environmental_impact FROM orchestration_jobs WHERE id = :job_id"),
                            {"job_id": job_id}
                        ).fetchone()
                        
                        total_cost_usd = float(job_row[0]) if job_row and job_row[0] is not None else 0.0
                        total_cost_twd = float(job_row[1]) if job_row and job_row[1] is not None else 0.0
                        
                        raw_env = job_row[2] if job_row else None
                        if isinstance(raw_env, str):
                            try:
                                raw_env = json.loads(raw_env)
                            except Exception:
                                raw_env = None
                        env_impact_json = json.dumps(raw_env) if isinstance(raw_env, dict) else None
                        
                        conn.execute(text("""
                            INSERT INTO exp_generated_contents 
                            (ablation_group, seed_config_id, run_id, content_type, content, job_id, rag_metrics, critic_scores, course_name, total_cost_usd, total_cost_twd, environmental_impact)
                            VALUES (:ablation_group, :seed_config_id, :run_id, :content_type, :content, :job_id, :rag_metrics, :critic_scores, :course_name, :total_cost_usd, :total_cost_twd, :environmental_impact)
                        """), {
                            "ablation_group": group,
                            "seed_config_id": seed_id,
                            "run_id": run_id,
                            "content_type": current_config.get("content_type", "unknown"),
                            "content": json.dumps(content) if isinstance(content, (dict, list)) else json.dumps({"text": content}),
                            "job_id": job_id,
                            "rag_metrics": json.dumps(rag_metrics),
                            "critic_scores": json.dumps(critic_scores),
                            "course_name": seed.get("course_name", "Unknown"),
                            "total_cost_usd": total_cost_usd,
                            "total_cost_twd": total_cost_twd,
                            "environmental_impact": env_impact_json
                        })
                    print(f"[{group}] Saved to exp_generated_contents (job_id: {job_id})")
                else:
                    error = final_state.get("error") or final_state.get("generation_errors")
                    print(f"[SKIP] seed_id={seed_id}, group={group} -- no final_generated_content returned. error={error}")
                    
            except Exception as e:
                import traceback
                print(f"[ERROR] seed_id={seed_id}, group={group} raised an exception: {e}")
                traceback.print_exc()
            finally:
                _clear_exp_context()

if __name__ == "__main__":
    asyncio.run(run_all())
