"""
Re-run Quality Critic for a single exp_generated_contents record whose
original call produced empty `quality_details` (Quality Critic parse failure).

Preserves the original `content` and `fact_critic` scores; only updates
`critic_scores.quality_details` and `critic_scores.quality_avg`.

Usage:
    python rerun_quality_critic_single.py               # dry-run (print only)
    python rerun_quality_critic_single.py --commit      # persist to DB
"""
import asyncio
import json
import os
import sys

repo_root   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_dir = os.path.join(repo_root, "backend")
sys.path.insert(0, backend_dir)  # for `from app.*`
sys.path.insert(0, repo_root)    # for `from backend.app.*`

from sqlalchemy import text

from app.utils.db_logger import engine
from app.agents.teacher_agent.critics.critic_db_utils import get_rag_chunks_by_job_id
from app.agents.teacher_agent.critics.quality_critic import QualityCritic
from langchain_openai import ChatOpenAI


TARGET_ID = 553
COMMIT = '--commit' in sys.argv


async def main():
    # ─── 1. Fetch record + seed config ───────────────────────────────
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT e.id, e.seed_config_id, e.ablation_group, e.run_id, e.content_type,
                   e.content, e.job_id, e.critic_scores,
                   s.input_config
            FROM exp_generated_contents e
            JOIN exp_seed_configs s ON s.id = e.seed_config_id
            WHERE e.id = :id
        """), {"id": TARGET_ID}).fetchone()

    if not row:
        print(f"[ERROR] id={TARGET_ID} not found"); return

    content_raw = row[5]
    if isinstance(content_raw, str):
        content = json.loads(content_raw)
    else:
        content = content_raw
    # run_all_experiments stores strings as {"text": content}; unwrap if so
    if isinstance(content, dict) and set(content.keys()) == {"text"}:
        content = content["text"]

    input_config = row[8] if isinstance(row[8], dict) else json.loads(row[8])
    content_type = row[4]
    job_id       = row[6]
    existing_cs  = row[7] if isinstance(row[7], dict) else json.loads(row[7])
    user_query   = input_config.get("prompt", "")

    print("─" * 60)
    print(f"Target record:")
    print(f"  id={row[0]}  seed={row[1]}  group={row[2]}  run_id={row[3]}")
    print(f"  content_type={content_type}  job_id={job_id}")
    print(f"  existing quality_avg={existing_cs.get('quality_avg')}")
    print(f"  existing quality_details len={len(existing_cs.get('quality_details', []))}")
    print(f"  fact_critic passed={existing_cs.get('fact_critic', {}).get('passed')}  "
          f"faithfulness={existing_cs.get('fact_critic', {}).get('faithfulness', {}).get('score')}")
    print(f"  user_query preview: {user_query[:80]!r}")
    print(f"  content preview: {str(content)[:200]!r}")
    print("─" * 60)

    # ─── 2. Invoke Quality Critic (same config as original) ──────────
    quality_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    quality_critic = QualityCritic(llm=quality_llm)

    print("Invoking Quality Critic...")
    if content_type == "exam":
        chunks = get_rag_chunks_by_job_id(job_id)
        context_str_combined = "\n".join([c["chunk_text"] for c in chunks])
        all_questions = []
        if isinstance(content, list):
            for block in content:
                questions = block.get("questions", [])
                for q in questions:
                    q["question_type"] = block.get("type", "unknown")
                all_questions.extend(questions)
        exam_data = {"type": "exam", "questions": all_questions}
        q_obj = await quality_critic.evaluate_exam(
            exam=exam_data, rag_content=context_str_combined,
            mode="quick", user_query=user_query,
        )
        q_res = q_obj.get("overall", {})
    else:
        q_res = await quality_critic.evaluate(content=content, user_query=user_query)

    new_details = q_res.get("evaluations", [])
    ratings = [e.get("rating", 0) for e in new_details]
    new_avg = sum(ratings) / len(ratings) if ratings else 0

    print("─" * 60)
    print(f"New Quality Critic result:")
    print(f"  quality_details length: {len(new_details)}")
    print(f"  quality_avg: {new_avg}")
    for e in new_details:
        print(f"    • {e.get('criteria', '')[:40]:<40}  rating={e.get('rating')}")
    print("─" * 60)

    if len(new_details) == 0:
        print("[ABORT] Critic still returned 0 evaluations. Not writing to DB.")
        return

    if len(new_details) != 6:
        print(f"[WARN] Expected 6 evaluations, got {len(new_details)}. Inspect before committing.")
        if not COMMIT:
            print("       (dry-run; exiting)")
            return

    # ─── 3. Update DB ────────────────────────────────────────────────
    updated_cs = dict(existing_cs)
    updated_cs["quality_details"] = new_details
    updated_cs["quality_avg"]     = new_avg
    # fact_critic 保留不動

    if not COMMIT:
        print("[DRY-RUN] Not writing to DB. Add --commit to persist.")
        return

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE exp_generated_contents
            SET critic_scores = CAST(:cs AS JSONB)
            WHERE id = :id
        """), {"cs": json.dumps(updated_cs, ensure_ascii=False), "id": TARGET_ID})
    print(f"✅ Updated exp_generated_contents id={TARGET_ID}")
    print(f"   (fact_critic preserved; quality_details and quality_avg updated)")


if __name__ == "__main__":
    asyncio.run(main())
