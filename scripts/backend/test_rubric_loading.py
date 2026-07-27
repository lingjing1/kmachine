
import sys
import os
from pathlib import Path
import json

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

try:
    from backend.app.core.prompt_manager import prompt_manager
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

def test_rubric_load():
    print("--- Testing Rubric Loading ---")
    try:
        rubrics = prompt_manager.get_prompt("critic_rubrics")
        if not rubrics:
            print("❌ Failed to load rubrics: prompt_manager returned empty/None.")
            sys.exit(1)
            
        print(f"Loaded {len(rubrics)} rubric categories.")
        
        expected_keys = ["Understandable", "Grammatical", "Logical_Consistency"]
        for key in expected_keys:
            if key in rubrics:
                print(f"✅ Found rubric: {key}")
            else:
                print(f"❌ Missing rubric: {key}")
                sys.exit(1)
        
        # Test content check
        desc = rubrics["Understandable"].get("description")
        print(f"Description for Understandable: {desc}")
        
    except Exception as e:
        print(f"❌ Rubric loading failed with exception: {e}")
        raise

if __name__ == "__main__":
    test_rubric_load()
