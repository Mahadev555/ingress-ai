from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


# Use JSONB on Postgres, plain JSON elsewhere (e.g. SQLite in dev/tests).
JsonList = JSON().with_variant(JSONB(), "postgresql")


class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    # The prefix is safe to show (it identifies a key); the full key is only
    # ever stored as a hash, so a database leak exposes no usable keys.
    key_prefix: Mapped[str] = mapped_column(String(24), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default")
    # Empty list means "any model is allowed".
    allowed_models: Mapped[list] = mapped_column(JsonList, default=list)
    token_budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Cost budget in USD; enforced alongside token_budget within budget_period.
    cost_budget_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Budget reset window: "total" (lifetime), "daily", or "monthly".
    budget_period: Mapped[str] = mapped_column(String(16), default="total")
    # Requests/minute for this key; None falls back to the global default.
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Tokens/minute (sliding window); None disables TPM limiting.
    tpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Max concurrent in-flight requests; None disables the concurrency cap.
    max_concurrency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelConfig(Base):
    """DB-backed model registry: overrides the AVAILABLE_MODELS env list with
    per-model pricing, aliases, default limits, and an enable/disable switch."""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    # If set, requests for `name` route to this target model instead.
    alias_of: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_price_per_1m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_price_per_1m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_tpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id: Mapped[int] = mapped_column(Integer, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=200)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    """Optional prompt/response capture (redacted), written only when
    AUDIT_CAPTURE_CONTENT is enabled. Correlated to usage via trace_id."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    # Groups the turns of one chat window into a single audit conversation.
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    key_id: Mapped[int] = mapped_column(Integer, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
