import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from backend.app.agents.rag_agent import rag_agent
from backend.app.config.settings import settings
from sqlalchemy import create_engine, text

def verify_rag():
    print(f"Hybrid Search Enabled: {settings.rag.use_hybrid_search}")
    print(f"Top K: {settings.rag.top_k}")
    
    # Check DB connection
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        # Get a valid unique_content_id
        result = conn.execute(text("SELECT id FROM unique_contents LIMIT 1")).fetchone()
        if not result:
            print("No content found in DB. Please ingest a document first.")
            return
        
        content_id = result[0]
        print(f"Testing with unique_content_id: {content_id}")
        
        # Test Query
        query = "測試查詢" # Use a generic query
        
        print("\n--- Running RAG Search ---")
        try:
            results = rag_agent.search(query, [content_id], top_k=3)
            print("Search successful!")
            print(f"Found {len(results.get('text_chunks', []))} text chunks.")
            
            for i, chunk in enumerate(results.get('text_chunks', [])):
                print(f"\nChunk {i+1}:")
                print(f"ID: {chunk['chunk_id']}")
                print(f"Score: {chunk.get('similarity_score')}")
                # Check if it has multimodal metadata
                print(f"Multimodal: {chunk.get('multimodal_metadata') is not None}")
                print(f"Text preview: {chunk['text'][:50]}...")
                
        except Exception as e:
            print(f"Search failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    verify_rag()
