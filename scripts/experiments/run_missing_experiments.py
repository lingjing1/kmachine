"""
Usage:
    python3 run_missing_experiments.py <run_id>

Given a run_id, this script:
1. Finds all seeds that appear under that run_id in exp_generated_contents.
2. Detects which of the 3 ablation groups (naive-rag, hybrid-rag, kp-hybrid-rag) are missing for each seed.
3. Re-runs only those missing (seed, group) combinations and inserts results using the SAME run_id.
"""

import asyncio
import json
import logging
import sys
import os
from sqlalchemy import text

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(repo_root, "backend"))


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
    """Call this before invoking the agent for each (seed, group) pair."""
    _exp_filter.seed_id = seed_id
    _exp_filter.group = group


def _clear_exp_context():
    _exp_filter.seed_id = "?"
    _exp_filter.group = "?"


def _attach_filter():
    """Attach filter to the root logger so ALL handlers pick it up."""
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(_exp_filter)

from app.utils.db_logger import engine, create_job
from app.agents.teacher_agent.graph import app as teacher_agent_app
from app.agents.teacher_agent.critics.critic_db_utils import get_rag_chunks_by_job_id
from app.agents.teacher_agent.critics.fact_critic import CustomFaithfulness, get_fact_critic_llm
from app.agents.teacher_agent.critics.quality_critic import QualityCritic

ALL_GROUPS = {"naive-rag", "hybrid-rag", "kp-hybrid-rag"}


def get_missing_combinations(run_id: str, min_seed: int = None, max_seed: int = None):
    """
    Returns a list of (seed_dict, group) tuples that are missing from exp_generated_contents
    for the given run_id.
    - If min_seed/max_seed are provided, it checks ALL seeds in that range.
    - Otherwise, it only checks seeds that already have at least one entry for this run_id.
    """
    with engine.connect() as conn:
        if min_seed is not None and max_seed is not None:
            # Check a specific range of seeds
            seeds_rows = conn.execute(text("""
                SELECT id, input_config, course_name, unit_id
                FROM exp_seed_configs
                WHERE id BETWEEN :min_id AND :max_id
            """), {"min_id": min_seed, "max_id": max_seed}).fetchall()
        else:
            # Seeds that participated in this run_id
            existing_seeds = conn.execute(text("""
                SELECT DISTINCT seed_config_id
                FROM exp_generated_contents
                WHERE run_id = :run_id
            """), {"run_id": run_id}).fetchall()

            if not existing_seeds:
                print(f"[ERROR] No records found for run_id={run_id}. Please check the run_id.")
                return []

            seed_ids = [r[0] for r in existing_seeds]
            placeholders = ", ".join(str(s) for s in seed_ids)
            seeds_rows = conn.execute(text(f"""
                SELECT id, input_config, course_name, unit_id
                FROM exp_seed_configs
                WHERE id IN ({placeholders})
            """)).fetchall()

        seed_map = {}
        for r in seeds_rows:
            seed_map[r[0]] = {
                "id": r[0],
                "input_config": r[1] if isinstance(r[1], dict) else json.loads(r[1]),
                "course_name": r[2],
                "unit_id": r[3],
            }

        # Now fetch what's already done for THESE seeds under this run_id
        target_ids = list(seed_map.keys())
        if not target_ids:
            return []

        placeholders = ", ".join(str(s) for s in target_ids)
        existing = conn.execute(text(f"""
            SELECT seed_config_id, ablation_group
            FROM exp_generated_contents
            WHERE run_id = :run_id AND seed_config_id IN ({placeholders})
        """), {"run_id": run_id}).fetchall()

        done_by_seed: dict[int, set] = {}
        for row in existing:
            seed_id, group = row[0], row[1]
            done_by_seed.setdefault(seed_id, set()).add(group)

    missing = []
    # Use seed_map.keys() to ensure we check all requested seeds
    for seed_id in sorted(seed_map.keys()):
        done_groups = done_by_seed.get(seed_id, set())
        missing_groups = ALL_GROUPS - done_groups
        for group in sorted(missing_groups):
            missing.append((seed_map[seed_id], group))

    return missing


async def run_missing(run_id: str, min_seed: int = None, max_seed: int = None):
    missing = get_missing_combinations(run_id, min_seed, max_seed)

    if not missing:
        print("No missing (seed, group) combinations found. Nothing to do.")
        return

    print(f"Found {len(missing)} missing combination(s) for run_id={run_id}:")
    for seed, group in missing:
        print(f"  seed_id={seed['id']}  group={group}")

    _attach_filter()

    for seed, group in missing:
        seed_id = seed["id"]
        config = seed["input_config"]
        unit_id = seed["unit_id"]

        _set_exp_context(seed_id, group)
        print(f"\n=== Running seed_id={seed_id}, group={group} (run_id={run_id}) ===")

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

        target_skill = (
            "exam_generation_skill"
            if current_config.get("content_type") == "exam"
            else "summarization_skill"
        )

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

            if not content:
                error = final_state.get("error") or final_state.get("generation_errors")
                print(f"[SKIP] seed_id={seed_id}, group={group} -- no final_generated_content. error={error}")
                continue

            print(f"[{group}] Generation successful.")

            # 1. RAG Metrics
            rag_metrics = {}
            with engine.connect() as conn:
                res = conn.execute(text(
                    "SELECT output FROM agent_tasks WHERE job_id=:j AND agent_name='retriever' ORDER BY id DESC LIMIT 1"
                ), {"j": job_id}).fetchone()
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
            critic_scores["quality_avg"] = sum(s) / len(s) if s else 0

            # 3. Insert into DB using the SAME run_id
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
                    (ablation_group, seed_config_id, run_id, content_type, content, job_id,
                     rag_metrics, critic_scores, course_name, total_cost_usd, total_cost_twd, environmental_impact)
                    VALUES
                    (:ablation_group, :seed_config_id, :run_id, :content_type, :content, :job_id,
                     :rag_metrics, :critic_scores, :course_name, :total_cost_usd, :total_cost_twd, :environmental_impact)
                """), {
                    "ablation_group": group,
                    "seed_config_id": seed_id,
                    "run_id": run_id,          # always the original run_id
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
            print(f"[{group}] Saved to exp_generated_contents (job_id={job_id}, run_id={run_id})")

        except Exception as e:
            import traceback
            print(f"[ERROR] seed_id={seed_id}, group={group} raised an exception: {e}")
            traceback.print_exc()
        finally:
            _clear_exp_context()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run missing experiment groups for a given run_id.")
    parser.add_argument("run_id", help="The original run_id to check.")
    parser.add_argument("--min_seed", type=int, help="Minimum seed_config_id to check.")
    parser.add_argument("--max_seed", type=int, help="Maximum seed_config_id to check.")

    args = parser.parse_args()

    asyncio.run(run_missing(args.run_id, args.min_seed, args.max_seed))
