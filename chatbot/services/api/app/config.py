"""
Application Configuration
=========================
Centralised settings loaded from environment variables.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings — loaded from .env file or environment."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "change-me-to-a-random-secret"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "mahlatini_chatbot"
    postgres_user: str = "mahlatini"
    postgres_password: str = "changeme_db_password"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "mahlatini_kb"

    # Groq Cloud
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Anthropic Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250929"

    # LLM provider
    default_provider: str = "groq"

    # Embedding
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # Crawler
    website_mirror_path: str = "/data/website"
    chunk_size: int = 800
    chunk_overlap: int = 150

    # n8n
    n8n_base_url: str = "http://n8n:5678"
    n8n_webhook_new_enquiry: str = "/webhook/new-enquiry"
    n8n_webhook_high_value: str = "/webhook/high-value-lead"
    n8n_webhook_escalation: str = "/webhook/escalation"
    n8n_webhook_booking_update: str = "/webhook/booking-update"
    n8n_webhook_website_enquiry: str = "/webhook/website-enquiry"
    n8n_webhook_secret: str = ""

    # Jira
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "MAHT"

    # Power BI
    powerbi_push_url: str = ""

    # Prompts
    prompts_dir: Path = Path("/app/prompts")

    # RAG
    rag_top_k: int = 5
    rag_confidence_high: float = 0.82
    rag_confidence_medium: float = 0.65

    # LLM tuning
    llm_temperature_chat: float = 0.75
    llm_temperature_caveat: float = 0.6
    llm_frequency_penalty: float = 0.3
    llm_presence_penalty: float = 0.3
    llm_max_tokens_chat: int = 300
    llm_compress_enabled: bool = True
    llm_compress_sentence_limit: int = 4

    # Session
    session_ttl_seconds: int = 86400  # 24 hours
    max_conversation_history: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
