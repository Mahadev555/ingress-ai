import asyncio
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


class TransientError(Exception):
    """A failure worth retrying / failing over: connection error or upstream
    5xx / 429. Carries what we need to relay if every attempt is exhausted."""

    def __init__(self, status_code: int, message: str, body: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.body = body


class ClientError(Exception):
    """A non-retryable upstream 4xx (except 429). The provider rejected the
    request itself, so retrying or failing over would not help — relay it."""

    def __init__(self, status_code: int, body: Optional[dict]) -> None:
        super().__init__(f"client error {status_code}")
        self.status_code = status_code
        self.body = body


@dataclass
class RetryConfig:
    attempts: int = 3
    base_delay: float = 0.05
    max_delay: float = 2.0


async def with_retries(
    factory: Callable[[], Awaitable[T]],
    config: RetryConfig,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Call ``factory`` until it succeeds or raises a non-transient error.

    Retries only on TransientError, with exponential backoff and full jitter.
    The last TransientError is re-raised once attempts are exhausted.
    """
    last_error: Optional[TransientError] = None
    for attempt in range(config.attempts):
        try:
            return await factory()
        except TransientError as error:
            last_error = error
            if attempt == config.attempts - 1:
                break
            backoff = min(config.max_delay, config.base_delay * (2**attempt))
            await sleep(random.uniform(0, backoff))
    assert last_error is not None
    raise last_error
