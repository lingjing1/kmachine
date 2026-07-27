
import yaml
import os
from pathlib import Path
from typing import Any, Dict, Optional

class SafeDict(dict):
    """A dictionary that returns the key itself in braces if missing, useful for partial formatting."""
    def __missing__(self, key):
        return '{' + key + '}'

class PromptManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptManager, cls).__new__(cls)
            cls._instance._prompts = {}
            cls._instance._file_mtimes = {}  # Track file modification times
            cls._instance._auto_reload = os.getenv("ENV", "development") == "development"  # Enable in dev mode
            cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self):
        """Loads all .yaml files from backend/app/config/prompts/"""
        # backend/app/core/prompt_manager.py -> backend/app/config/prompts
        base_path = Path(__file__).resolve().parent.parent / "config" / "prompts"
        
        if not base_path.exists():
            return

        # Clear existing prompts before reloading
        self._prompts = {}
        
        for yaml_file in base_path.glob("*.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data:
                        self._prompts.update(data)
                
                self._file_mtimes[str(yaml_file)] = yaml_file.stat().st_mtime
                
            except Exception as e:
                print(f"Error loading prompt file {yaml_file}: {e}")

    def _check_and_reload(self):
        """Check if any YAML files have been modified and reload if necessary.
        In development mode, always reloads to immediately reflect YAML edits.
        """
        if not self._auto_reload:
            return

        base_path = Path(__file__).resolve().parent.parent / "config" / "prompts"
        if not base_path.exists():
            return

        needs_reload = False
        for yaml_file in base_path.glob("*.yaml"):
            file_path = str(yaml_file)
            current_mtime = yaml_file.stat().st_mtime
            if file_path not in self._file_mtimes or self._file_mtimes[file_path] < current_mtime:
                needs_reload = True
                break

        if needs_reload:
            print("[PromptManager] YAML change detected — reloading prompts from disk.", flush=True)
            self._load_prompts()

    def get_prompt(self, key_path: str, **kwargs) -> str:
        """
        Get a prompt by dot-separated path (e.g. 'summarization.system_prompt').
        Supports formatting with **kwargs and automatically injects variables from the 'common' block.
        Unknown placeholders are preserved for later formatting.
        """
        self._check_and_reload()
        
        keys = key_path.split('.')
        value = self._prompts
        
        try:
            for key in keys:
                value = value[key]
            
            if isinstance(value, str):
                # Prepare formatting arguments
                final_kwargs = SafeDict()
                
                # 1. Inject global 'common' variables (lowest priority)
                if 'common' in self._prompts and isinstance(self._prompts['common'], dict):
                    final_kwargs.update(self._prompts['common'])
                
                # 2. Inject namespace-specific common variables (if applicable)
                # Example: for 'summarization.preview_user', look for 'summarization.common'
                if len(keys) > 1:
                    namespace = keys[0]
                    if namespace in self._prompts and isinstance(self._prompts[namespace], dict):
                        ns_common = self._prompts[namespace].get('common')
                        if isinstance(ns_common, dict):
                            final_kwargs.update(ns_common)

                # 3. Inject user-provided kwargs (highest priority)
                final_kwargs.update(kwargs)
                
                # Use format_map to safely handle missing keys (like runtime variables)
                return value.format_map(final_kwargs)
            else:
                return value
                
        except (KeyError, TypeError, AttributeError):
            print(f"Warning: Prompt key '{key_path}' not found.")
            return f"MISSING_PROMPT: {key_path}"

    def reload(self):
        """Manually reloads prompts from disk."""
        self._load_prompts()

# Singleton instance
prompt_manager = PromptManager()
