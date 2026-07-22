import math
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import require_key
from app.core.auth import KeyContext
from app.core.config import get_settings
from app.core.ratelimit import bucket_name, bucket_params
from app.resilience.fallback import Failure, Success, execute_with_fallback
from app.resilience.retry import RetryConfig
from app.router.selector import build_candidates
from app.schemas.unified import ChatCompletionRequest

router = APIRouter()

_STATUS_ERROR_TYPES = {502: "bad_gateway", 503: "upstream_unavailable"}


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionRequest,
    request: Request,
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
    # use the first healthy candidate.
    if payload.stream:
        breaker = request.app.state.circuit_breaker
        candidate = next(
            (c for c in candidates if not breaker.is_open(c.provider)), candidates[0]
        )
        stream_payload = payload.model_copy(update={"model": candidate.model})
        return StreamingResponse(
            candidate.adapter.stream(stream_payload, candidate.creds, client),
            media_type="text/event-stream",
        )

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
        unified = outcome.candidate.adapter.parse_response(outcome.response.json())
        return JSONResponse(content=unified.model_dump(exclude_none=True))

    return _error_response(outcome)


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
