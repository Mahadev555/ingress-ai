import json
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


async def _metered_stream(source, usage_holder: dict):
    """Relay the guarded stream, capturing the usage chunk as it passes."""
    async for chunk in _guarded_stream(source):
        _sniff_usage(chunk, usage_holder)
        yield chunk


def _sniff_usage(chunk: bytes, usage_holder: dict) -> None:
    """Pull token counts out of an OpenAI-style usage chunk, if present."""
    for line in chunk.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            continue
        try:
            usage = json.loads(data).get("usage")
        except ValueError:
            continue
        if usage:
            usage_holder["prompt_tokens"] = usage.get("prompt_tokens", 0)
            usage_holder["completion_tokens"] = usage.get("completion_tokens", 0)
            usage_holder["total_tokens"] = usage.get(
                "total_tokens",
                usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            )


async def _record_stream_usage(session_factory, key, provider, model, usage_holder, started):
    """Record a streamed request's usage once the stream has drained."""
    event = UsageEvent(
        key_id=key.key_id,
        tenant_id=key.tenant_id,
        provider=provider,
        model=model,
        prompt_tokens=usage_holder["prompt_tokens"],
        completion_tokens=usage_holder["completion_tokens"],
        total_tokens=usage_holder["total_tokens"],
        cost_usd=cost_usd(model, usage_holder["prompt_tokens"], usage_holder["completion_tokens"]),
        latency_ms=int((time.perf_counter() - started) * 1000),
        status=200,
        cache_hit=False,
    )
    observe(event)
    await record_usage(session_factory, event)


@router.get("/models")
async def list_models() -> dict:
    """OpenAI-compatible model list, driven by the AVAILABLE_MODELS setting.
    Public (no key) so clients can discover models before authenticating."""
    settings = get_settings()
    data = [
        {"id": model, "object": "model", "owned_by": provider_for_model(model)}
        for model in settings.model_list()
    ]
    return {"object": "list", "data": data}


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
        # Sniff the final usage chunk as the stream flows, then record real
        # tokens/cost once it finishes (the background task runs after that).
        usage_holder = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        background.add_task(
            _record_stream_usage,
            request.app.state.session_factory,
            key,
            candidate.provider,
            candidate.model,
            usage_holder,
            started,
        )
        return StreamingResponse(
            _metered_stream(source, usage_holder),
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
