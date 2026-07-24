import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLog, UsageRecord, VirtualKey
from app.observability.logging import redact
from app.schemas.usage import UsageEvent

logger = logging.getLogger("ingress.usage")

_MAX_AUDIT_CHARS = 8000


async def write_audit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    trace_id: str | None,
    conversation_id: str | None,
    key_id: int,
    tenant_id: str,
    provider: str,
    model: str,
    prompt: str,
    response: str,
) -> None:
    """Persist a redacted prompt/response pair. Best-effort, off the hot path."""
    try:
        async with session_factory() as session:
            session.add(
                AuditLog(
                    trace_id=trace_id,
                    conversation_id=conversation_id,
                    key_id=key_id,
                    tenant_id=tenant_id,
                    provider=provider,
                    model=model,
                    prompt=redact(prompt)[:_MAX_AUDIT_CHARS],
                    response=redact(response)[:_MAX_AUDIT_CHARS],
                )
            )
            await session.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to write audit log")


async def touch_last_used(
    session_factory: async_sessionmaker[AsyncSession], key_id: int
) -> None:
    """Stamp a key's last_used_at. Off the hot path; best-effort."""
    try:
        async with session_factory() as session:
            await session.execute(
                update(VirtualKey)
                .where(VirtualKey.id == key_id)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to update last_used_at")


async def record_usage(
    session_factory: async_sessionmaker[AsyncSession], event: UsageEvent
) -> None:
    """Persist a usage record. Best-effort: accounting must never break a
    request that already produced a response."""
    try:
        async with session_factory() as session:
            session.add(
                UsageRecord(
                    key_id=event.key_id,
                    tenant_id=event.tenant_id,
                    tags=event.tags,
                    provider=event.provider,
                    model=event.model,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                    total_tokens=event.total_tokens,
                    cost_usd=event.cost_usd,
                    latency_ms=event.latency_ms,
                    status=event.status,
                    cache_hit=event.cache_hit,
                    trace_id=event.trace_id,
                )
            )
            await session.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to write usage record")
