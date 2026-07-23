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

    # Models advertised by GET /v1/models (comma-separated). Any model whose
    # name matches a registry prefix still routes even if not listed here.
    available_models: str = (
        "gpt-4o-mini,gpt-4o,"
        "claude-3-5-sonnet,claude-3-5-haiku,"
        "gemini-1.5-flash,gemini-1.5-pro,"
        "gemini-2.0-flash,gemini-2.0-flash-lite,gemini-3.1-flash-lite"
    )

    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"

    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2024-02-15-preview"

    # Shared infrastructure.
    # SQLite by default for zero-config local dev; set DATABASE_URL to a
    # Postgres DSN (postgresql+asyncpg://...) in production.
    database_url: str = "sqlite+aiosqlite:///./ingress.db"
    redis_url: str = "redis://localhost:6379/0"

    # Admin API for key management; requests must send this as X-Admin-Token.
    admin_api_key: str = ""
    # Additional full-admin tokens (comma-separated), beyond admin_api_key.
    admin_tokens: str = ""

    # Rate limiting (token bucket, per key + model).
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    # "memory" (single instance / dev) or "redis" (multi-replica production).
    rate_limit_backend: str = "memory"

    # Resilience: retry (per candidate) + circuit breaker (per provider).
    retry_attempts: int = 3
    retry_base_delay: float = 0.05
    retry_max_delay: float = 2.0
    circuit_fail_threshold: int = 5
    circuit_reset_seconds: float = 30.0

    # Exact-match response cache.
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    # "memory" (single instance / dev) or "redis" (multi-replica production).
    cache_backend: str = "memory"

    # Upstream HTTP timeout, in seconds.
    request_timeout: float = 60.0

    # Observability / audit.
    # Capture redacted prompt+response text to the audit_logs table (off by default).
    audit_capture_content: bool = False

    # Playground: max turns per chat window before forcing a new conversation.
    max_conversation_turns: int = 5

    # Guardrails.
    max_request_bytes: int = 1_000_000  # reject bodies larger than this (413)
    max_output_tokens_cap: int = 0  # clamp requested max_tokens to this (0 = no cap)
    guardrails_enabled: bool = False  # simple prompt-injection screening
    admin_read_tokens: str = ""  # comma-separated read-only admin tokens

    def model_list(self) -> list[str]:
        """Parse the comma-separated `available_models` into a clean list."""
        return [m.strip() for m in self.available_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
