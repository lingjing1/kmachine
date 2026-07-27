
import sys
import os
import json
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.app.config.settings import settings
from backend.app.agents.teacher_agent.ingestion import ingest_course_content
from backend.app.agents.teacher_agent.rag_agent import rag_agent

def verify_flow():
    db_url = settings.database_url
    engine = create_engine(db_url)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            print("1. Setting up mock data...")
            # 1. Create a dummy course
            course_res = conn.execute(text("INSERT INTO courses (name, semester_name, created_at) VALUES ('Test Course Gen', 'Testing', NOW()) RETURNING id")).fetchone()
            course_id = course_res[0]

            # 1.5 Get User ID
            user_res = conn.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
            if not user_res:
                # Create user if not exists
                user_res = conn.execute(text("INSERT INTO users (email, full_name) VALUES ('test@example.com', 'Tester') RETURNING id")).fetchone()
            user_id = user_res[0]

            # 1.6 Create Orchestration Job
            job_res = conn.execute(text("INSERT INTO orchestration_jobs (user_id, status, created_at) VALUES (:uid, 'completed', NOW()) RETURNING id"), {"uid": user_id}).fetchone()
            job_id = job_res[0]

            # 1.7 Create Agent Task
            task_res = conn.execute(text("""
                INSERT INTO agent_tasks (job_id, agent_name, status, created_at) 
                VALUES (:jid, 'test_agent', 'completed', NOW()) RETURNING id
            """), {"jid": job_id}).fetchone()
            task_id = task_res[0]

            # 2. Create dummy generated content entry
            gen_res = conn.execute(text("""
                INSERT INTO generated_contents (
                    source_agent_task_id, content_type, title, content, created_at
                ) VALUES (
                    :tid, 'material', 'Test Generated Material', 
                    :content, NOW()
                ) RETURNING id
            """), {
                "tid": task_id,
                "content": json.dumps({"text": "This is a test generated content used for verifying RAG ingestion. It contains specific keywords like Polyphenol and Flavanol."})
            }).fetchone()
            gen_id = gen_res[0]

            # 3. Create course_contents entry linked to it
            cc_res = conn.execute(text("""
                INSERT INTO course_contents (
                    course_id, title, content_type, source_type, source_id, content, created_at, updated_at
                ) VALUES (
                    :cid, 'Test Gen Unit', 'material', 'generated_content', :sid, :content, NOW(), NOW()
                ) RETURNING id
            """), {
                "cid": course_id,
                "sid": gen_id,
                "content": json.dumps({"text": "The content text is here: Artificial Intelligence is transforming education via RAG systems."})
            }).fetchone()
            course_content_id = cc_res[0]
            
            print(f"   Created Course Content ID: {course_content_id}")

            trans.commit()
            
            print("2. Running Ingestion...")
            # Run ingestion
            success = ingest_course_content(course_content_id, force_reprocess=True)
            if not success:
                print("❌ Ingestion failed!")
                return

            print("✅ Ingestion successful.")

            print("3. Verifying RAG Retrieval...")
            # Search for keyword in the content
            results = rag_agent.search(
                user_prompt="transforming education",
                unique_content_ids=[], # No uploaded docs
                generated_course_content_ids=[course_content_id],
                top_k=5
            )

            print(f"   RAG returned {len(results['text_chunks'])} chunks.")
            
            found = False
            for chunk in results['text_chunks']:
                print(f"   - Chunk ID: {chunk['chunk_id']}")
                print(f"   - Text: {chunk['text'][:50]}...")
                if "Artificial Intelligence" in chunk['text']:
                    found = True
                if str(chunk['chunk_id']).startswith("gen_"):
                    print("   ✅ ID prefix is correct (gen_)")
                else:
                    print(f"   ❌ ID prefix incorrect: {chunk['chunk_id']}")

            if found:
                print("✅ RAG successfully retrieved the generated content.")
            else:
                print("❌ RAG did not find the expected content.")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            print("4. Cleaning up...")
            # Use a new connection for cleanup to ensure no transaction conflict
            with engine.connect() as cleanup_conn:
                with cleanup_conn.begin():
                     if 'course_content_id' in locals():
                         cleanup_conn.execute(text("DELETE FROM generated_content_chunks WHERE course_content_id = :id"), {"id": course_content_id})
                         cleanup_conn.execute(text("DELETE FROM course_contents WHERE id = :id"), {"id": course_content_id})
                     if 'gen_id' in locals():
                         cleanup_conn.execute(text("DELETE FROM generated_contents WHERE id = :id"), {"id": gen_id})
                     if 'task_id' in locals():
                         cleanup_conn.execute(text("DELETE FROM agent_tasks WHERE id = :id"), {"id": task_id})
                     if 'job_id' in locals():
                         cleanup_conn.execute(text("DELETE FROM orchestration_jobs WHERE id = :id"), {"id": job_id})
                     if 'course_id' in locals():
                         cleanup_conn.execute(text("DELETE FROM courses WHERE id = :id"), {"id": course_id})
            print("Done.")

if __name__ == "__main__":
    verify_flow()
