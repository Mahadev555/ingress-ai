from typing import Any

async def fallback_chain(candidates: list[Any], call_fn):
    for candidate in candidates:
        try:
            return await call_fn(candidate)
        except Exception:
            continue
    raise RuntimeError("all providers failed")
