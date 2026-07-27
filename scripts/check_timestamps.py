import asyncio
import os
import sys

# Allow import from backend
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.app.db import engine
from sqlalchemy import text
from datetime import datetime

async def main():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT created_at FROM uploaded_contents LIMIT 1")).fetchone()
        if result and result.created_at:
            dt = result.created_at
            
            print(f"Original from DB: {dt}")
            print(f"Has tzinfo? {dt.tzinfo is not None}")
            
            # This is the logic we added to the routers
            formatted = dt.isoformat() if dt.tzinfo else dt.isoformat() + 'Z'
            print(f"API Output will be: {formatted}")
            
if __name__ == "__main__":
    asyncio.run(main())
