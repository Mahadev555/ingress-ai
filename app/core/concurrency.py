"""In-process per-key concurrency limiter.

Tracks in-flight requests per virtual key. Process-local (like the in-memory
rate limiter): fine for a single instance; a multi-replica deployment would back
this with Redis. The event loop is single-threaded, so the check-then-increment
in ``acquire`` is atomic as long as it contains no ``await``.
"""


class ConcurrencyLimiter:
    def __init__(self) -> None:
        self._inflight: dict[int, int] = {}

    def acquire(self, key_id: int, limit: int | None) -> bool:
        if not limit or limit <= 0:
            return True
        current = self._inflight.get(key_id, 0)
        if current >= limit:
            return False
        self._inflight[key_id] = current + 1
        return True

    def release(self, key_id: int) -> None:
        current = self._inflight.get(key_id, 0)
        if current <= 1:
            self._inflight.pop(key_id, None)
        else:
            self._inflight[key_id] = current - 1
