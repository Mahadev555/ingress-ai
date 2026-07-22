from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Upstream providers.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"

    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2024-02-15-preview"

    # Shared infrastructure (used from later build days).
    redis_url: str = "redis://localhost:6379/0"
    postgres_url: str = "postgresql+asyncpg://localhost/ingress_ai"

    # Upstream HTTP timeout, in seconds.
    request_timeout: float = 60.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
