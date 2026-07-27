
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

try:
    from backend.app.config.settings import settings
    from backend.app.core.prompt_manager import prompt_manager
except ImportError as e:
    print(f"ImportError: {e}")
    # Force add paths if needed
    sys.exit(1)

def test_settings_load():
    print("--- Testing Settings Loading ---")
    try:
        print(f"Database URL: {settings.database_url[:15]}...")
        print(f"RAG Chunk Size: {settings.rag.chunk_size}")
        print(f"Agent Model: {settings.agent.generator_model}")
        print("✅ Settings loaded successfully.")
    except Exception as e:
        print(f"❌ Settings loading failed: {e}")
        raise

def test_prompt_manager_load():
    print("\n--- Testing Prompt Manager ---")
    try:
        summarization_sys = prompt_manager.get_prompt("summarization.system_prompt")
        print(f"Summarization System Prompt Preview: {summarization_sys[:50]}...")
        
        exam_plan = prompt_manager.get_prompt("exam_generator.plan_system")
        print(f"Exam Plan System Prompt Preview: {exam_plan[:50]}...")
        
        quality_focus = prompt_manager.get_prompt("quality.focus.Understandable")
        print(f"Quality Focus Preview: {quality_focus[:50]}...")
        
        if "MISSING_PROMPT" in summarization_sys or "MISSING_PROMPT" in exam_plan:
            print("❌ Failed to load some prompts.")
            sys.exit(1)
            
        # Test System Prompt match
        sys_prompt = prompt_manager.get_prompt("system.common.educational_expert")
        if sys_prompt and "expert in creating educational materials" in sys_prompt:
             print(f"✅ System Prompt 'educational_expert' loaded correctly.")
        else:
             print(f"❌ System Prompt 'educational_expert' invalid: {sys_prompt}")
             sys.exit(1)
        
        print("✅ Prompts loaded successfully.")
    except Exception as e:
        print(f"❌ Prompt loading failed: {e}")
        raise

if __name__ == "__main__":
    try:
        test_settings_load()
        test_prompt_manager_load()
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        sys.exit(1)
