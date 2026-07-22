from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Upstream provider (OpenAI passthrough for now).
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Shared infrastructure (used from later build days).
    redis_url: str = "redis://localhost:6379/0"
    postgres_url: str = "postgresql+asyncpg://localhost/ingress_ai"

    # Upstream HTTP timeout, in seconds.
    request_timeout: float = 60.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
