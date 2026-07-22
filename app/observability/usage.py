import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import UsageRecord
from app.schemas.usage import UsageEvent

logger = logging.getLogger("ingress.usage")


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
                    provider=event.provider,
                    model=event.model,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                    total_tokens=event.total_tokens,
                    cost_usd=event.cost_usd,
                    latency_ms=event.latency_ms,
                    status=event.status,
                    cache_hit=event.cache_hit,
                )
            )
            await session.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to write usage record")
