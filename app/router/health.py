from typing import Any

async def mark_provider_unhealthy(provider: str) -> None:
    # TODO: track provider health and circuit-breaker state in Redis
    return

async def is_provider_healthy(provider: str) -> bool:
    # TODO: return whether provider is healthy
    return True
