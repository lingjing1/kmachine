import sys
from sqlalchemy import text, inspect
from backend.app.db import engine
from datetime import datetime, timedelta

def fix_timestamps():
    with engine.connect() as conn:
        insp = inspect(engine)
        tables = insp.get_table_names()
        
        print(f"Checking {len(tables)} tables...")
        
        for table in tables:
            try:
                columns = insp.get_columns(table)
                for col in columns:
                    col_name = col['name']
                    col_type = str(col['type']).lower()
                    
                    if 'timestamp' in col_type:
                        print(f"Processing {table}.{col_name} ({col_type})...")
                        
                        # 1. Alter to TIMESTAMP WITHOUT TIME ZONE if it's WITH TIME ZONE
                        if 'with time zone' in col_type:
                            print(f"  - Altering {table}.{col_name} to WITHOUT TIME ZONE")
                            conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{col_name}" TYPE TIMESTAMP WITHOUT TIME ZONE;'))
                        
                        # 2. Shift future records back by 8 hours
                        # We identify "future" as records >= '2026-03-07' in local time
                        # Actually, better to check if it's significantly ahead of now.
                        # local_now = datetime.now() # This is Taipei time on the server
                        # Let's just use the user specified cutoff '2026-03-07' as significant.
                        
                        check_q = text(f'SELECT count(*) FROM "{table}" WHERE "{col_name}" >= \'2026-03-07\'')
                        count = conn.execute(check_q).scalar()
                        
                        if count > 0:
                            print(f"  - Found {count} future records. Shifting back by 8 hours...")
                            update_q = text(f'UPDATE "{table}" SET "{col_name}" = "{col_name}" - INTERVAL \'8 hours\' WHERE "{col_name}" >= \'2026-03-07\'')
                            conn.execute(update_q)
                        
                conn.commit()
            except Exception as e:
                print(f"Error processing table {table}: {e}")
                conn.rollback()

if __name__ == "__main__":
    fix_timestamps()
    print("Database timestamp fix completed.")
