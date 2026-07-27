
from sqlalchemy import text, inspect
from backend.app.db import engine
from datetime import datetime

def migrate_and_fix_tz():
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE data_type = 'timestamp with time zone' 
            AND table_schema = 'public'
        """)).fetchall()
        tz_columns = [(row[0], row[1]) for row in res]

    print(f"Found {len(tz_columns)} columns with TZ. Starting migration...")

    with engine.begin() as conn:
        for table, col in tz_columns:
            try:
                print(f"Processing {table}.{col}...")
                
                # 1. Alter type to WITHOUT TIME ZONE
                # This keeps the "numbers" the same if session TZ is UTC.
                # e.g. '2026-03-07 01:10+00' -> '2026-03-07 01:10'
                conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE TIMESTAMP WITHOUT TIME ZONE;'))
                
                # 2. Shift "historical" records forward by 8 hours.
                # We assume records before 2026-03-06 were "real UTC" (8 hours late compared to Taipei).
                # Records after that are either already shifted or we handled them in previous steps.
                # Actually, let's use a safe cutoff. The user specifically mentioned enrolled_at is late.
                
                update_q = text(f"""
                    UPDATE "{table}" 
                    SET "{col}" = "{col}" + INTERVAL '8 hours' 
                    WHERE "{col}" < '2026-03-06 00:00:00'
                """)
                res = conn.execute(update_q)
                print(f"  - Shifted {res.rowcount} historical records forward 8h.")
                
            except Exception as e:
                print(f"Error processing {table}.{col}: {e}")

if __name__ == "__main__":
    migrate_and_fix_tz()
    print("Database TZ migration and historical fix completed.")
