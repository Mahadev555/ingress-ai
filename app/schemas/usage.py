from dataclasses import dataclass
from typing import Optional


@dataclass
class UsageEvent:
    """One request's accounting: who, which provider/model, tokens, cost,
    latency, status, and whether it was a cache hit."""

    key_id: int
    tenant_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    status: int
    cache_hit: bool
    trace_id: Optional[str] = None
