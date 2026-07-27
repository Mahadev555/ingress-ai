from dataclasses import dataclass, field
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
    # "chat" (LLM request) or "tool" (MCP tool call). For tool calls, provider
    # carries the server name and model carries the tool name.
    kind: str = "chat"
    trace_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
