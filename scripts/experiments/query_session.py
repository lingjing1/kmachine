import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, text

# Try to import from app
try:
    from app.core.config import settings
    DATABASE_URL = settings.DATABASE_URL
except Exception:
    import os
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cookai:cookai@localhost/cookai")

engine = create_engine(DATABASE_URL)

def default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

session_id = "b4cf6e33-72d3-4e66-8541-0087c1e66f9d"

queries = {
    "1. Session Info (student_learning_sessions)": f"SELECT id, user_id, course_id, unit_id, started_at, last_active_at, is_completed, context_data FROM student_learning_sessions WHERE id = '{session_id}';",
    "2. Reading Logs & Citations (material_reading_logs)": f"SELECT id, content_id, stay_duration_seconds, max_scroll_depth, citation_interactions, exit_action, created_at FROM material_reading_logs WHERE unit_session_id = '{session_id}' ORDER BY created_at ASC;",
    "3. Chatbot Dialogs (student_chatbot_dialogs)": f"SELECT id, role, content, created_at FROM student_chatbot_dialogs WHERE unit_session_id = '{session_id}' ORDER BY created_at ASC;",
    "4. Question Logs (student_question_logs)": f"SELECT id, question_id, knowledge_point_id, stage, CAST(answer AS TEXT) as answer_text, correctness, answered_at FROM student_question_logs WHERE unit_session_id = '{session_id}' ORDER BY answered_at ASC;"
}

results = {}

with engine.connect() as conn:
    for name, query in queries.items():
        try:
            res = conn.execute(text(query))
            rows = [dict(mapping) for mapping in res.mappings()]
            results[name] = rows
        except Exception as e:
            results[name] = [{"error": str(e)}]

print(json.dumps(results, default=default_serializer, indent=2, ensure_ascii=False))
