import asyncio
import random

async def retry_async(fn, retries: int = 3, base_delay: float = 0.5):
    last_exc = None
    for attempt in range(retries):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt) + random.random() * 0.1
            await asyncio.sleep(delay)
    raise last_exc
