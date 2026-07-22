from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.schemas.usage import UsageEvent

REQUESTS = Counter(
    "ingress_requests_total",
    "Total chat completion requests.",
    ["provider", "model", "status", "cache"],
)
LATENCY = Histogram(
    "ingress_request_latency_seconds",
    "End-to-end request latency.",
    ["provider", "model"],
)
TOKENS = Counter(
    "ingress_tokens_total",
    "Tokens processed.",
    ["provider", "model", "kind"],
)
COST = Counter(
    "ingress_cost_usd_total",
    "Estimated spend in USD.",
    ["provider", "model"],
)


def observe(event: UsageEvent) -> None:
    cache = "hit" if event.cache_hit else "miss"
    REQUESTS.labels(event.provider, event.model, str(event.status), cache).inc()
    LATENCY.labels(event.provider, event.model).observe(event.latency_ms / 1000)
    TOKENS.labels(event.provider, event.model, "prompt").inc(event.prompt_tokens)
    TOKENS.labels(event.provider, event.model, "completion").inc(event.completion_tokens)
    COST.labels(event.provider, event.model).inc(event.cost_usd)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
