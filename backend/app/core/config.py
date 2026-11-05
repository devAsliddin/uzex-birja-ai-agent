"""Application configuration using pydantic-settings.

Values are read from environment variables and the ``.env`` file.
Never commit real secrets to version control — use ``.env.example`` as a template.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "UZEX AI Backend"
    app_env: str = "development"
    debug: bool = True
    api_v1_str: str = "/api/v1"
    backend_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    host: str = "127.0.0.1"
    port: int = 8000

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./birja.db"
    test_database_url: str = "sqlite+aiosqlite:///./test_uzex_ai.db"
    ai_read_database_url: str | None = None
    alembic_database_url: str | None = None

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str | None = None

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    secret_key: str = "change-me-to-a-strong-random-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12
    api_key_header: str = "X-API-Key"

    # Rate limiting (requests per minute per client)
    rate_limit_default: int = 100
    rate_limit_auth: int = 20
    rate_limit_ai: int = 30
    rate_limit_export: int = 10

    # ------------------------------------------------------------------
    # AI / LLM provider abstraction
    # ------------------------------------------------------------------
    ai_provider: str = "mock"
    ai_model: str = "uzex-ai-mock"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "uzex-ai"

    ai_temperature: float = 0.1
    ai_max_tokens: int = 1024
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 3
    ai_retry_backoff_seconds: int = 2

    # AI read-only database user (PostgreSQL production)
    ai_db_user: str = "uzex_ai_reader"
    ai_db_password: str = "uzex_reader_password"

    # ------------------------------------------------------------------
    # Admin bootstrap
    # ------------------------------------------------------------------
    admin_email: str = "admin@uzex.local"
    admin_password: str = "admin-password-change-me"

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    import_batch_size: int = 5000
    export_max_rows: int = 500_000
    cache_ttl_seconds: int = 600
    data_dir: str = "../data"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()
