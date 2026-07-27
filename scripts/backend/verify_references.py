import sys
from typing import List, Dict

import os
import io
import contextlib
from datetime import datetime
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.getcwd())

# Mock database engine to avoid actual DB connection issues during simple logic verification
# We will mock the `create_engine` and `engine.connect` calls in `metadata_enrichment.py`
# But since we import it, we need to mock it BEFORE import or patch it.
# Patching is easier.

from backend.app.agents.teacher_agent.utils.metadata_enrichment import enrich_chunk_metadata
from backend.app.agents.teacher_agent.utils.exam_citation_validator import ExamCitationValidator

# Mock data
mock_chunks = [
    {"chunk_id": 1, "source_content_id": 101, "source_pages": [1], "search_text": "Chunk 1 text about photosynthesis.", "text": "Photosynthesis is the process by which plants use sunlight."},
    {"chunk_id": 2, "source_content_id": 102, "source_pages": [5], "search_text": "Chunk 2 text about mitochondria.", "text": "Mitochondria are the powerhouse of the cell."}
]

mock_page_content = [
    {
        "source_document_id": 101,
        "page_number": 1,
        "content": [
            {"type": "text", "text": "Photosynthesis is the process by which plants use sunlight. It produces glucose and oxygen."},
            {"type": "image", "base64": "base64_image_data_1", "caption": "Leaf structure"}
        ],
        "combined_human_text": "Photosynthesis is the process by which plants use sunlight. It produces glucose and oxygen."
    }
]

mock_source_ids = [101, 102]

# Mock Database Interaction
# We need to mock sqlalchemy.create_engine inside the module
import backend.app.agents.teacher_agent.utils.metadata_enrichment as me_module

# Mock the result of fetching document info
# doc_info_list result: [(id, filename, uploaded_at)]
mock_doc_rows = [
    MagicMock(unique_content_id=101, file_name="Biology_Ch1.pdf", created_at=datetime(2023, 1, 15)),
    MagicMock(unique_content_id=102, file_name="Biology_Ch2.pdf", created_at=datetime(2023, 2, 20))
]

# We need to mock sqlalchemy.Table to avoid autoload interaction
from unittest.mock import patch, Mock

# Create a mock for the table column that passes SQLAlchemy's checks
# SQLAlchemy checks if it has 'expression' attribute or similar traits
class MockColumn:
    def __init__(self, name):
        self.name = name
    
    def __eq__(self, other):
        return True # Simplified equality
    
    def in_(self, other):
        return True

class MockTable:
    def __init__(self, name, metadata, autoload_with=None):
        self.c = Mock()
        self.c = Mock()
        self.c.id = MockColumn("id")
        self.c.unique_content_id = MockColumn("unique_content_id")
        self.c.file_name = MockColumn("file_name")
        self.c.created_at = MockColumn("created_at")

@patch('backend.app.agents.teacher_agent.utils.metadata_enrichment.Table', side_effect=MockTable)
@patch('backend.app.agents.teacher_agent.utils.metadata_enrichment.select')
def run_verification(mock_select, mock_table_cls):
    # Setup mock select to return a dummy object that we can verify calls against if needed
    # But mainly we need engine.connect.execute to return rows
    
    # We need to mock engine.connect() return value in the module
    mock_engine = MagicMock()
    mock_connection = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_connection
    mock_connection.execute.return_value.fetchall.return_value = mock_doc_rows
    
    # Inject mock engine
    me_module.engine = mock_engine

    # --- Test 1: Metadata Enrichment ---
    print("--- Test 1: Metadata Enrichment ---")
    enriched_chunks = enrich_chunk_metadata(mock_chunks, mock_page_content, mock_source_ids)

    for chunk in enriched_chunks:
        meta = chunk["source_metadata"]
        print(f"Chunk {chunk['chunk_id']}:")
        print(f"  Doc: {meta['document_name']} (ID: {meta['document_id']})")
        print(f"  Uploaded: {meta['uploaded_at']}")
        print(f"  Has Images: {meta['has_images']}")
        if meta['has_images']:
            print(f"  Image Count: {len(meta['images'])}")
            print(f"  First Image Caption: {meta['images'][0]['caption']}")

    # Verification Checks
    assert len(enriched_chunks) == 2
    assert enriched_chunks[0]["source_metadata"]["document_name"] == "Biology_Ch1.pdf"
    assert enriched_chunks[0]["source_metadata"]["has_images"] == True
    assert enriched_chunks[1]["source_metadata"]["document_name"] == "Biology_Ch2.pdf"
    assert enriched_chunks[1]["source_metadata"]["has_images"] == False

    print("✅ Metadata Enrichment Passed!")

    # --- Test 2: Citation Validation ---
    print("\n--- Test 2: Citation Validation ---")
    # Pass page content to validator
    validator = ExamCitationValidator(enriched_chunks, mock_page_content)

    # Case 1: Valid Citation
    generated_valid = [
        {
            "question_text": "What is photosynthesis?",
            "source": {
                "chunk_ids": [1],
                "evidence": "Photosynthesis is the process", # Partial match
                "page_number": 1
            }
        }
    ]
    result_valid = validator.validate(generated_valid)
    print(f"Valid Check: {result_valid['valid']}")
    assert result_valid['valid'] == True

    # Case 2: Invalid Chunk ID
    generated_invalid_id = [
        {
            "question_text": "What is magic?",
            "source": {
                "chunk_ids": [999], # Invalid
                "evidence": "Photosynthesis is the process",
                "page_number": 1
            }
        }
    ]
    result_invalid_id = validator.validate(generated_invalid_id)
    print(f"Invalid ID Check: {result_invalid_id['valid']} (Expected False)")
    assert result_invalid_id['valid'] == False
    assert result_invalid_id['errors'][0]['type'] == 'invalid_chunk_id'

    # Case 3: Evidence Not Found
    generated_invalid_evidence = [
        {
            "question_text": "What is photosynthesis?",
            "source": {
                "chunk_ids": [1],
                "evidence": "Xenon gas is inert and noble", # Completely unrelated content
                "page_number": 1
            }
        }
    ]
    result_invalid_evidence = validator.validate(generated_invalid_evidence)
    print(f"Invalid Evidence Check: {result_invalid_evidence['valid']} (Expected False)")
    assert result_invalid_evidence['valid'] == False
    assert result_invalid_evidence['errors'][0]['type'] == 'evidence_mismatch'

    print("✅ Citation Validation Passed!")

    # Case 4: Missing Chunk ID (Should Auto-Inject)
    print("\n--- Test 3: Auto-Injection of Chunk IDs ---")
    generated_missing_id = [
        {
            "question_text": "What is photosynthesis?",
            "source": {
                # "chunk_ids": [], # Missing
                "evidence": "Photosynthesis is the process", 
                "page_number": 1
            }
        }
    ]
    # Note: validation modifies the input in-place if implemented correctly, or we check return errors which should be empty
    result_missing_id = validator.validate(generated_missing_id)
    print(f"Auto-Inject Check: {result_missing_id['valid']}")
    
    injected_ids = generated_missing_id[0]["source"].get("chunk_ids")
    print(f"Injected Chunk IDs: {injected_ids}")
    
    assert result_missing_id['valid'] == True
    assert injected_ids == [1] # Should find chunk 1
    
    print("✅ Chunk ID Auto-Injection Passed!")

    
    # Case 5: Fuzzy Match Test (Simulate LLM minor hallucination)
    print("\n--- Test 4: Fuzzy Match Test (Simulating LLM behavior) ---")
    chunk_text = "Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize foods from carbon dioxide and water."
    # Simulate LLM dropping "green" and "some other", and changing punctuation
    llm_evidence = "Photosynthesis is the process by which plants and organisms use sunlight to synthesize foods from carbon dioxide and water" 
    
    generated_fuzzy = [
        {
            "question_text": "What is photosynthesis?",
            "source": {
                "evidence": llm_evidence, 
                "page_number": 1
            }
        }
    ]
    
    # Inject a chunk that matches partially
    validator.chunk_map[101] = {"chunk_id": 101, "text": chunk_text}
    validator.chunk_ids.add(101)
    
    result_fuzzy = validator.validate(generated_fuzzy)
    print(f"Fuzzy Match Check: {result_fuzzy['valid']}")
    
    
    # Expect success now with fuzzy matching
    if result_fuzzy['valid']:
        print("✅ Fuzzy matching PASSED as expected!")
        injected_fuzzy_ids = generated_fuzzy[0]["source"].get("chunk_ids")
        print(f"   Fuzzy matched Chunk IDs: {injected_fuzzy_ids}")
        assert injected_fuzzy_ids == [101]
    else:
        print("❌ Fuzzy matching unexpectedly failed.")
        assert False, "Fuzzy matching should have passed."

    # Case 6: User Reported Chinese Fuzzy Match Issue
    print("\n--- Test 5: Chinese Fuzzy Match Test (User Scenario) ---")
    # Real chunk text (Simulate potential OCR mess or slightly different text)
    cn_chunk_text = "資料前處理(Data Preprocessing)是將原始數據進行清理、轉換和整理的過程，目的是為了提高數據質量。"
    # LLM Generated Evidence (Slightly summarized, missing english, punctuation diff)
    cn_evidence = "資料前處理是將原始資料進行清理、轉換和整理，以提高數據質量和一致性。"
    
    # Inject 
    validator.chunk_map[202] = {"chunk_id": 202, "text": cn_chunk_text}
    validator.chunk_ids.add(202)
    
    generated_cn = [
        {
            "question_text": "什麼是資料前處理？",
            "source": {
                "evidence": cn_evidence, 
                "page_number": 5
            }
        }
    ]
    
    result_cn = validator.validate(generated_cn)
    print(f"Chinese Fuzzy Check: {result_cn['valid']}")
    
    if result_cn['valid']:
        print("✅ Chinese fuzzy matching PASSED!")
        injected_ids = result_cn['errors']
    else:
        print("❌ Chinese fuzzy matching FAILED.")
        # If it fails, let's see why (threshold issues?)

    # Case 7: Page Content Fallback Test
    print("\n--- Test 6: Page Content Fallback Test ---")
    # Evidence is in Page 1 ("It produces glucose and oxygen") but NOT in Chunk 1 ("Photosynthesis is the process... sunlight.")
    page_evidence = "It produces glucose and oxygen"
    
    generated_page_fallback = [
        {
            "question_text": "What does it produce?",
            "source": {
                "evidence": page_evidence, 
                "page_number": 1
            }
        }
    ]
    
    result_fallback = validator.validate(generated_page_fallback)
    print(f"Page Fallback Check: {result_fallback['valid']}")
    
    if result_fallback['valid']:
        print("✅ Page Fallback matching PASSED!")
        injected_ids = generated_page_fallback[0]["source"].get("chunk_ids")
        print(f"   Mapped to Chunk IDs: {injected_ids}")
        assert injected_ids == [1] # Should map to Chunk 1 (anchor for Page 1)
    else:
        print("❌ Page Fallback matching FAILED.")
        assert False, "Page Fallback matching should have passed."


if __name__ == "__main__":
    run_verification()
