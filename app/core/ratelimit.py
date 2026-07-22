import time
from dataclasses import dataclass
from typing import Optional, Protocol

from app.core.config import Settings

# Atomic token-bucket refill + consume. Keeps the read-modify-write on the Redis
# server so concurrent replicas can't race. Returns [allowed, tokens, retry_s].
_TOKEN_BUCKET_LUA = """
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed = 0
local retry = 0
if tokens >= cost then
  allowed = 1
  tokens = tokens - cost
else
  retry = (cost - tokens) / rate
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000))
return {allowed, tostring(tokens), tostring(retry)}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after: float  # seconds until the request could succeed


class RateLimiter(Protocol):
    async def acquire(
        self, bucket: str, rate: float, capacity: float, cost: float = 1.0
    ) -> RateLimitResult: ...

    async def close(self) -> None: ...


class InMemoryTokenBucket:
    """Process-local token bucket. Fine for a single instance, dev, and tests;
    use the Redis backend when running more than one replica."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(
        self, bucket: str, rate: float, capacity: float, cost: float = 1.0
    ) -> RateLimitResult:
        now = time.monotonic()
        tokens, ts = self._buckets.get(bucket, (capacity, now))
        tokens = min(capacity, tokens + max(0.0, now - ts) * rate)

        if tokens >= cost:
            tokens -= cost
            self._buckets[bucket] = (tokens, now)
            return RateLimitResult(allowed=True, remaining=tokens, retry_after=0.0)

        self._buckets[bucket] = (tokens, now)
        retry_after = (cost - tokens) / rate if rate > 0 else 0.0
        return RateLimitResult(allowed=False, remaining=tokens, retry_after=retry_after)

    async def close(self) -> None:
        self._buckets.clear()


class RedisTokenBucket:
    """Distributed token bucket backed by a Redis Lua script."""

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._script = self._redis.register_script(_TOKEN_BUCKET_LUA)

    async def acquire(
        self, bucket: str, rate: float, capacity: float, cost: float = 1.0
    ) -> RateLimitResult:
        allowed, tokens, retry = await self._script(
            keys=[bucket], args=[rate, capacity, time.time(), cost]
        )
        return RateLimitResult(
            allowed=bool(int(allowed)),
            remaining=float(tokens),
            retry_after=float(retry),
        )

    async def close(self) -> None:
        await self._redis.aclose()


def create_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisTokenBucket(settings.redis_url)
    return InMemoryTokenBucket()


def bucket_params(per_minute: int) -> tuple[float, float]:
    """Translate a requests-per-minute limit into (refill_rate, capacity)."""
    return per_minute / 60.0, float(per_minute)


def bucket_name(key_id: int, model: str) -> str:
    return f"ratelimit:{key_id}:{model}"
