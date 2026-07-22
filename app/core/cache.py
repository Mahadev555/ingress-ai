import hashlib
import json
import time
from typing import Any, Optional, Protocol

from app.core.config import Settings
from app.schemas.unified import GATEWAY_ONLY_FIELDS, ChatCompletionRequest


class Cache(Protocol):
    async def get(self, key: str) -> Optional[dict]: ...

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None: ...

    async def close(self) -> None: ...


class InMemoryCache:
    """Process-local cache with per-entry TTL. Fine for a single instance and
    tests; use the Redis backend to share a cache across replicas."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, dict]] = {}

    async def get(self, key: str) -> Optional[dict]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    async def close(self) -> None:
        self._store.clear()


class RedisCache:
    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> Optional[dict]:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        await self._redis.set(key, json.dumps(value), ex=ttl_seconds)

    async def close(self) -> None:
        await self._redis.aclose()


def create_cache(settings: Settings) -> Cache:
    if settings.cache_backend == "redis":
        return RedisCache(settings.redis_url)
    return InMemoryCache()


def cache_key(payload: ChatCompletionRequest, tenant_id: str) -> str:
    """Deterministic key for an exact-match lookup.

    Built from the provider-relevant request fields (gateway-only fields and
    `stream` excluded) plus the tenant, so a cache is never shared across
    tenants. Serialization is sorted so key order never changes the hash.
    """
    normalized: dict[str, Any] = payload.model_dump(
        exclude_none=True, exclude=GATEWAY_ONLY_FIELDS | {"stream"}
    )
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode()).hexdigest()
    return f"cache:{tenant_id}:{digest}"
