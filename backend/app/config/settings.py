
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Robustly find the .env file
# backend/app/config/settings.py → Cook.ai/.env
ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"

class RagSettings(BaseSettings):
    chunk_size: int = Field(default=700, validation_alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, validation_alias="CHUNK_OVERLAP")
    use_hybrid_search: bool = Field(default=True, validation_alias="USE_HYBRID_SEARCH")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="EMBEDDING_MODEL")
    top_k: int = Field(default=10, validation_alias="RAG_TOP_K")
    
    # Development & Debug Settings
    force_ingest: bool = Field(default=False, validation_alias="FORCE_INGEST")
    enable_rag_auto_evaluation: bool = Field(default=True, validation_alias="ENABLE_RAG_AUTO_EVALUATION")
    
    # KP Query Enhancement (Phase 3 optimization)
    enable_kp_query_enhancement: bool = Field(default=True, validation_alias="ENABLE_KP_QUERY_ENHANCEMENT")

    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra="ignore")

class AgentSettings(BaseSettings):
    main_orchestrator_model: str = Field(default="gpt-4o-mini", validation_alias="MAIN_ORCHESTRATOR_MODEL")
    generator_model: str = Field(default="gpt-4o-mini", validation_alias="GENERATOR_MODEL")
    vision_model: str = Field(default="gpt-4o-mini", validation_alias="VISION_MODEL")
    vision_enabled: bool = Field(default=True, validation_alias="USE_VISION_LLM")
    max_images_per_prompt: int = Field(default=2, validation_alias="MAX_IMAGES_PER_PROMPT")

    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra="ignore")

class LangSmithSettings(BaseSettings):
    tracing_v2: bool = Field(default=False, validation_alias="LANGCHAIN_TRACING_V2")
    endpoint: str = Field(default="https://api.smith.langchain.com", validation_alias="LANGCHAIN_ENDPOINT")
    api_key: str = Field(default="", validation_alias="LANGCHAIN_API_KEY")
    project: str = Field(default="default", validation_alias="LANGCHAIN_PROJECT")
    
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra="ignore")

class Settings(BaseSettings):
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    # oj_database_url removed from here to avoid duplicate

    # Grouped Settings
    rag: RagSettings = Field(default_factory=RagSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)

    # Email Settings
    smtp_host: str = Field(default="smtp.gmail.com", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")

    # Storage Settings
    # Default: project_root/backend/storage/uploads
    upload_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "storage" / "uploads",
        validation_alias="UPLOAD_DIR"
    )
    # Unified with upload_dir
    attachment_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "storage" / "uploads",
        validation_alias="ATTACHMENT_DIR"
    )
    
    # BERT Settings
    # Default to local model path if not specified in env
    bert_model_path: str = Field(
        default=str(Path(__file__).resolve().parent.parent.parent / "models" / "bert_mastery" / "final_model"),
        validation_alias="BERT_MODEL_PATH"
    )
    bert_device: Optional[str] = Field(default=None, validation_alias="BERT_DEVICE")

    # OJ Database
    oj_database_url: Optional[str] = Field(default=None, validation_alias="OJ_DATABASE_URL")

    # JWT Authentication Settings
    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        validation_alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=180,
        validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # Experiment course IDs — these courses apply strict AI question exclusion.
    # Courses in this list will not receive questions tagged as 'AI generated' in recommendations.
    # All other courses are relaxed (AI-generated questions are allowed).
    # Configure in .env as: EXPERIMENT_COURSE_IDS=[5, 12, 18]
    experiment_course_ids: List[int] = Field(
        default=[],
        validation_alias="EXPERIMENT_COURSE_IDS"
    )

    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra="ignore")

# Singleton instance
settings = Settings()
