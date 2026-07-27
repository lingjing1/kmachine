
from sqlalchemy import text, inspect
from backend.app.db import engine
from datetime import datetime

def fix_all_timestamps():
    # We'll shift back records that fall into the "suspiciously shifted" range.
    # Since the fix was applied around 01:00 on 3/7, anything before that 
    # but after say 3/6 08:00 might be shifted by 8 hours.
    # Actually, to be safe, we can shift everything from 3/6 00:00 to 3/7 01:00.
    
    cutoff_start = '2026-03-06 00:00:00'
    cutoff_end = '2026-03-07 01:00:00'
    
    tables_to_check = [
        ('feedback_reports', 'created_at'),
        ('material_ratings', 'created_at'),
        ('generated_contents', 'updated_at'),
        ('generated_contents', 'created_at'),
        ('reference_feedbacks', 'created_at'),
        ('orchestration_jobs', 'created_at'),
        ('orchestration_jobs', 'updated_at'),
        ('attachment_reading_logs', 'created_at'),
        ('generator_setting_logs', 'created_at'),
        ('student_question_logs', 'answered_at'),
        ('users', 'created_time'),
    ]
    
    with engine.begin() as conn:
        for table, col in tables_to_check:
            try:
                # Check if table and column exist
                res = conn.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' AND column_name = '{col}'
                """)).scalar()
                
                if res == 0:
                    print(f"Skipping {table}.{col} (not found)")
                    continue
                
                # Count records in the window
                count_q = text(f"SELECT COUNT(*) FROM \"{table}\" WHERE \"{col}\" BETWEEN '{cutoff_start}' AND '{cutoff_end}'")
                count = conn.execute(count_q).scalar()
                
                if count > 0:
                    print(f"Fixing {table}.{col}: found {count} records. Shifting back 8 hours.")
                    update_q = text(f"""
                        UPDATE "{table}" 
                        SET "{col}" = "{col}" - INTERVAL '8 hours' 
                        WHERE "{col}" BETWEEN '{cutoff_start}' AND '{cutoff_end}'
                    """)
                    conn.execute(update_q)
                else:
                    print(f"No records to fix in {table}.{col}")
                    
            except Exception as e:
                print(f"Error fixing {table}.{col}: {e}")

if __name__ == "__main__":
    fix_all_timestamps()
    print("Full database timestamp fix completed.")
