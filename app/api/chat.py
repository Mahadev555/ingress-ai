import logging
import math
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import require_key
from app.core.auth import KeyContext
from app.core.cache import cache_key
from app.core.config import get_settings
from app.core.ratelimit import bucket_name, bucket_params
from app.observability.metrics import observe
from app.observability.pricing import cost_usd
from app.observability.usage import record_usage
from app.providers.registry import provider_for_model
from app.resilience.fallback import Failure, Success, execute_with_fallback
from app.resilience.retry import RetryConfig
from app.router.selector import build_candidates
from app.schemas.unified import ChatCompletionRequest
from app.schemas.usage import UsageEvent

logger = logging.getLogger("ingress.chat")

router = APIRouter()

_STATUS_ERROR_TYPES = {502: "bad_gateway", 503: "upstream_unavailable"}

# Disable proxy buffering so SSE chunks reach the client immediately.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _guarded_stream(source):
    """Relay an adapter's SSE stream, turning a mid-stream failure into a clean
    terminal error event instead of a dropped/hung connection."""
    try:
        async for chunk in source:
            yield chunk
    except Exception:
        logger.exception("streaming failed")
        yield b'data: {"error": {"message": "stream interrupted", "type": "stream_error"}}\n\n'
        yield b"data: [DONE]\n\n"


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionRequest,
    request: Request,
    background: BackgroundTasks,
    key: KeyContext = Depends(require_key),
) -> Any:
    if not key.allows_model(payload.model):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "message": f"model {payload.model!r} is not allowed for this key",
                    "type": "model_not_allowed",
                }
            },
        )

    settings = get_settings()
    started = time.perf_counter()

    if settings.rate_limit_enabled:
        rate, capacity = bucket_params(settings.rate_limit_per_minute)
        limit = await request.app.state.rate_limiter.acquire(
            bucket_name(key.key_id, payload.model), rate, capacity
        )
        if not limit.allowed:
            return _rate_limited(limit.retry_after)

    client: httpx.AsyncClient = request.app.state.http_client
    candidates = build_candidates(payload.model, payload.fallbacks or [], settings)

    # Streaming holds a live connection, so fail-over isn't possible mid-stream;
    # use the first healthy candidate. Streaming responses are not cached.
    if payload.stream:
        breaker = request.app.state.circuit_breaker
        candidate = next(
            (c for c in candidates if not breaker.is_open(c.provider)), candidates[0]
        )
        stream_payload = payload.model_copy(update={"model": candidate.model})
        source = candidate.adapter.stream(stream_payload, candidate.creds, client)
        # Latency is measured after the stream drains (background runs then).
        _record(request, background, key, candidate.provider, candidate.model,
                None, 200, cache_hit=False, started=started)
        return StreamingResponse(
            _guarded_stream(source),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    cache = request.app.state.cache
    key_str = cache_key(payload, key.tenant_id) if settings.cache_enabled else None

    if key_str is not None:
        cached = await cache.get(key_str)
        if cached is not None:
            logger.info("cache hit model=%s tenant=%s", payload.model, key.tenant_id)
            _record(request, background, key, provider_for_model(payload.model),
                    payload.model, cached, 200, cache_hit=True, started=started)
            return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

    outcome = await execute_with_fallback(
        candidates,
        payload,
        client,
        request.app.state.circuit_breaker,
        RetryConfig(
            attempts=settings.retry_attempts,
            base_delay=settings.retry_base_delay,
            max_delay=settings.retry_max_delay,
        ),
    )

    if isinstance(outcome, Success):
        body = outcome.candidate.adapter.parse_response(outcome.response.json()).model_dump(
            exclude_none=True
        )
        if key_str is not None:
            await cache.set(key_str, body, settings.cache_ttl_seconds)
        _record(request, background, key, outcome.candidate.provider,
                outcome.candidate.model, body, 200, cache_hit=False, started=started)
        return JSONResponse(content=body, headers={"X-Cache": "MISS"})

    _record(request, background, key, candidates[0].provider, payload.model,
            None, outcome.status_code, cache_hit=False, started=started)
    return _error_response(outcome)


def _record(
    request: Request,
    background: BackgroundTasks,
    key: KeyContext,
    provider: str,
    model: str,
    body: Optional[dict],
    status: int,
    cache_hit: bool,
    started: float,
) -> None:
    """Update Prometheus metrics now and persist the usage record after the
    response is sent (off the request's hot path and DB session)."""
    usage = (body or {}).get("usage") or {}
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    event = UsageEvent(
        key_id=key.key_id,
        tenant_id=key.tenant_id,
        provider=provider,
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=usage.get("total_tokens", prompt + completion),
        cost_usd=cost_usd(model, prompt, completion),
        latency_ms=int((time.perf_counter() - started) * 1000),
        status=status,
        cache_hit=cache_hit,
    )
    observe(event)
    background.add_task(record_usage, request.app.state.session_factory, event)


def _error_response(failure: Failure) -> JSONResponse:
    body = failure.body or {
        "error": {
            "message": failure.message,
            "type": _STATUS_ERROR_TYPES.get(failure.status_code, "upstream_error"),
        }
    }
    return JSONResponse(status_code=failure.status_code, content=body)


def _rate_limited(retry_after: float) -> JSONResponse:
    retry_seconds = max(1, math.ceil(retry_after))
    return JSONResponse(
        status_code=429,
        content={"error": {"message": "rate limit exceeded", "type": "rate_limit_exceeded"}},
        headers={"Retry-After": str(retry_seconds)},
    )
