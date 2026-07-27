import sys
import os

# Ensure backend module can be imported
sys.path.append(os.getcwd())

from sqlalchemy import text
from backend.app.db import engine

def check_and_create_indexes():
    with engine.connect() as conn:
        print("Checking indexes...")
        
        # Helper to check existence
        def index_exists(table, index):
            query = text(f"SELECT 1 FROM pg_indexes WHERE tablename = '{table}' AND indexname = '{index}'")
            return conn.execute(query).scalar() is not None

        indexes = [
            ("course_contents", "idx_course_contents_course_id", "CREATE INDEX idx_course_contents_course_id ON course_contents(course_id)"),
            ("course_contents", "idx_course_contents_source_id", "CREATE INDEX idx_course_contents_source_id ON course_contents(source_id, source_type)"),
            ("generated_contents", "idx_generated_contents_task_id", "CREATE INDEX idx_generated_contents_task_id ON generated_contents(source_agent_task_id)"),
            ("attachments", "idx_attachments_polymorphic", "CREATE INDEX idx_attachments_polymorphic ON attachments(attachable_type, attachable_id)"),
        ]

        for table, index, create_cmd in indexes:
            try:
                if not index_exists(table, index):
                    print(f"Creating missing index: {index} on {table}")
                    conn.execute(text(create_cmd))
                    conn.commit()
                else:
                    print(f"Index {index} on {table} already exists.")
            except Exception as e:
                print(f"Error checking/creating index {index} on {table}: {e}")
        
        print("Index check complete.")

if __name__ == "__main__":
    check_and_create_indexes()
