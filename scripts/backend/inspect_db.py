
import sqlalchemy
from sqlalchemy import text
from backend.app.utils.db_logger import engine

def inspect_tables():
    with engine.connect() as conn:
        for table in ['submissions_assignment', 'submissions_exam']:
            try:
                print(f"--- Table: {table} ---")
                
                # Check constraints
                constraints = conn.execute(text(f"SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = '{table}'::regclass")).fetchall()
                print("Constraints:")
                for c in constraints:
                    print(f"  {c[0]} ({c[1]}): {c[2]}")
                    
                # Check indices
                indices = conn.execute(text(f"SELECT indexname, indexdef FROM pg_indexes WHERE tablename = '{table}'")).fetchall()
                print("Indices:")
                for i in indices:
                    print(f"  {i[0]}: {i[1]}")

            except Exception as e:
                print(f"Error inspecting {table}: {e}")

if __name__ == "__main__":
    inspect_tables()
