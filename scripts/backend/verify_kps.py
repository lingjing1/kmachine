
import sys
import os
from sqlalchemy import text

# Add backend to sys.path
sys.path.append('/home/monica/Cook.ai/backend')

from app.db import engine
from app.routers.teacher_course_router import _sync_get_content_knowledge_points

def verify():
    print("Verifying KP fetching logic...")
    try:
        with engine.connect() as conn:
            # Get a valid unique_content_id and course_id
            result = conn.execute(text("SELECT unique_content_id, course_id, knowledge_point_name FROM document_knowledge_points LIMIT 1"))
            row = result.fetchone()
            if not row:
                print("No data in document_knowledge_points")
                return

            unique_content_id = row[0]
            course_id = row[1]
            kp_name = row[2]
            
            print(f"Testing with unique_content_id={unique_content_id}, course_id={course_id}, expected KP={kp_name}")

            # Call the function
            kps = _sync_get_content_knowledge_points(course_id, [unique_content_id])
            
            print(f"Returned KPs: {kps}")
            
            # Verify
            found = False
            for kp in kps:
                if kp['name'] == kp_name:
                    found = True
                    break
            
            if found:
                print("SUCCESS: Expected KP found in response.")
            else:
                print("FAILURE: Expected KP not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify()
