import json
import logging
import math
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _bearer_token, require_key
from app.core.auth import KeyContext, resolve_key, tokens_in_last_minute
from app.core.cache import cache_key
from app.core.config import get_settings
from app.core.guardrails import screen_text
from app.core.ratelimit import bucket_name, bucket_params
from app.db.session import get_session
from app.observability.alerts import check_key_budget
from app.observability.metrics import observe
from app.observability.pricing import cost_usd
from app.observability.usage import record_usage, touch_last_used, write_audit
from app.providers.base import EmbeddingsUnsupported, UpstreamStreamError
from app.providers.registry import creds_for_provider, resolve_provider, ADAPTERS
from app.schemas.embeddings import EmbeddingRequest
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


async def _metered_stream(first: bytes | None, stream, usage_holder: dict, on_done=None):
    """Relay a stream whose first chunk was already pulled (to check status),
    capturing usage as it flows. A failure *after* start becomes a clean
    terminal error event rather than a dropped connection. `on_done` runs once
    the stream fully drains (used to release the per-key concurrency slot)."""
    try:
        if first is not None:
            _sniff_usage(first, usage_holder)
            yield first
        async for chunk in stream:
            _sniff_usage(chunk, usage_holder)
            yield chunk
    except Exception:
        logger.exception("streaming failed after start")
        yield b'data: {"error": {"message": "stream interrupted", "type": "stream_error"}}\n\n'
        yield b"data: [DONE]\n\n"
    finally:
        if on_done is not None:
            on_done()


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
        )
    return "" if content is None else str(content)


def _message_text(message) -> str:
    return f"{message.role}: {_content_text(message.content)}"


def _maybe_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost, or 0.0 when cost tracking is turned off."""
    if not get_settings().cost_tracking_enabled:
        return 0.0
    return cost_usd(model, prompt_tokens, completion_tokens)


def _merge_tags(key_tags, header: Optional[str]) -> list[str]:
    """Key's default tags plus any per-request tags from the X-Tags header."""
    tags = list(key_tags or [])
    if header:
        for raw in header.split(","):
            tag = raw.strip()
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def _latest_user_prompt(messages) -> str:
    """The most recent user message only — clients resend the whole history on
    every turn, so auditing that would duplicate prior turns. One pair per entry."""
    for message in reversed(messages):
        if message.role == "user":
            return _content_text(message.content)
    return ""


def _response_text(body: dict) -> str:
    choices = body.get("choices") or []
    return "".join((c.get("message") or {}).get("content") or "" for c in choices)


def _sniff_usage(chunk: bytes, usage_holder: dict) -> None:
    """Pull token counts (and, for audit, the assistant text) out of the SSE
    chunks as they flow past."""
    for line in chunk.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        usage = obj.get("usage")
        if usage:
            usage_holder["prompt_tokens"] = usage.get("prompt_tokens", 0)
            usage_holder["completion_tokens"] = usage.get("completion_tokens", 0)
            usage_holder["total_tokens"] = usage.get(
                "total_tokens",
                usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            )
        try:
            delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        except (AttributeError, IndexError):
            delta = None
        if delta:
            usage_holder["content"] = usage_holder.get("content", "") + delta


async def _record_stream_usage(
    session_factory, key, provider, model, usage_holder, started,
    trace_id=None, audit=False, prompt="", conversation_id=None, tags=None,
):
    """Record a streamed request's usage (and audit its content) once the
    stream has drained — the assistant text was accumulated as it flowed."""
    event = UsageEvent(
        key_id=key.key_id,
        tenant_id=key.tenant_id,
        provider=provider,
        model=model,
        prompt_tokens=usage_holder["prompt_tokens"],
        completion_tokens=usage_holder["completion_tokens"],
        total_tokens=usage_holder["total_tokens"],
        cost_usd=_maybe_cost(model, usage_holder["prompt_tokens"], usage_holder["completion_tokens"]),
        latency_ms=int((time.perf_counter() - started) * 1000),
        status=200,
        cache_hit=False,
        trace_id=trace_id,
        tags=tags or [],
    )
    observe(event)
    await record_usage(session_factory, event)
    if audit:
        await write_audit(
            session_factory,
            trace_id=trace_id,
            conversation_id=conversation_id,
            key_id=key.key_id,
            tenant_id=key.tenant_id,
            provider=provider,
            model=model,
            prompt=prompt,
            response=usage_holder.get("content", ""),
        )


@router.get("/models")
async def list_models(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """OpenAI-compatible model list. Driven by the DB model registry when it has
    entries, otherwise the AVAILABLE_MODELS env list. If a valid virtual key is
    supplied it's filtered to that key's allowed models; otherwise it's public."""
    registry = request.app.state.model_registry
    names = registry.enabled_names() if not registry.is_empty() else get_settings().model_list()

    # Optional per-key filtering — only narrow the list when a real key is sent.
    token = _bearer_token(authorization)
    if token:
        key = await resolve_key(session, token)
        if key and key.allowed_models:
            names = [m for m in names if key.allows_model(m)]

    data = [
        {"id": model, "object": "model", "owned_by": resolve_provider(model)}
        for model in names
    ]
    return {"object": "list", "data": data}


@router.get("/config")
async def client_config() -> dict:
    """Public client-facing config (e.g. the playground's conversation limit and
    whether cost tracking is on, which the dashboard uses to show/hide cost)."""
    settings = get_settings()
    return {
        "max_conversation_turns": settings.max_conversation_turns,
        "cost_tracking_enabled": settings.cost_tracking_enabled,
        # Providers the gateway has an adapter for (the full supported palette).
        "providers": sorted(ADAPTERS.keys()),
    }


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionRequest,
    request: Request,
    background: BackgroundTasks,
    key: KeyContext = Depends(require_key),
    session: AsyncSession = Depends(get_session),
    x_conversation_id: Optional[str] = Header(default=None),
    x_tags: Optional[str] = Header(default=None),
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

    if key.budget_exceeded():
        return _budget_exceeded(key)

    settings = get_settings()
    started = time.perf_counter()
    tags = _merge_tags(key.tags, x_tags)

    # Fire a budget alert (soft/hard) off the hot path when configured.
    if settings.alert_webhook_url:
        background.add_task(
            check_key_budget,
            request.app.state.http_client,
            settings.alert_webhook_url,
            settings.alert_soft_threshold,
            key,
        )

    # Resolve a registry alias to its target model, then read that model's
    # default limits (a key's own limit still wins over the model default).
    registry = request.app.state.model_registry
    resolved = registry.resolve_alias(payload.model)
    if resolved != payload.model:
        payload = payload.model_copy(update={"model": resolved})
    default_rpm, default_tpm = registry.defaults(payload.model)

    # Guardrails: clamp requested output tokens and screen for prompt injection.
    if settings.max_output_tokens_cap > 0:
        if not payload.max_tokens or payload.max_tokens > settings.max_output_tokens_cap:
            payload = payload.model_copy(update={"max_tokens": settings.max_output_tokens_cap})

    if settings.guardrails_enabled:
        prompt_text = "\n".join(_message_text(m) for m in payload.messages)
        reason = screen_text(prompt_text)
        if reason:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": reason, "type": "guardrail_blocked"}},
            )

    if settings.rate_limit_enabled:
        per_minute = key.rate_limit_per_minute or default_rpm or settings.rate_limit_per_minute
        rate, capacity = bucket_params(per_minute)
        limit = await request.app.state.rate_limiter.acquire(
            bucket_name(key.key_id, payload.model), rate, capacity
        )
        if not limit.allowed:
            return _rate_limited(limit.retry_after)

    # Tokens-per-minute limit: reject if the last 60s already exceed the cap.
    tpm_limit = key.tpm_limit or default_tpm
    if tpm_limit:
        used = await tokens_in_last_minute(session, key.key_id)
        if used >= tpm_limit:
            return _tpm_limited(tpm_limit, used)

    # Per-key concurrency cap (in-flight requests). Released on every exit path;
    # for a stream, only after the whole stream has drained.
    concurrency = request.app.state.concurrency
    if not concurrency.acquire(key.key_id, key.max_concurrency):
        return _concurrency_limited(key.max_concurrency)

    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            concurrency.release(key.key_id)

    handed_off = False
    background.add_task(touch_last_used, request.app.state.session_factory, key.key_id)

    try:
        client: httpx.AsyncClient = request.app.state.http_client
        deployments = request.app.state.deployment_registry
        candidates = build_candidates(
            payload.model, payload.fallbacks or [], settings,
            deployments=deployments, strategy=settings.routing_strategy,
        )

        # Drop providers with no API key configured — a clean error beats a
        # cryptic "illegal header" from an empty Bearer token. Fallbacks still work.
        configured = [c for c in candidates if c.creds.api_key]
        if not configured:
            return _not_configured(candidates[0].provider)
        candidates = configured

        # Streaming holds a live connection, so fail-over isn't possible mid-stream;
        # use the first healthy candidate. Streaming responses are not cached.
        if payload.stream:
            breaker = request.app.state.circuit_breaker
            candidate = next(
                (c for c in candidates if not breaker.is_open(c.provider)), candidates[0]
            )
            stream_payload = payload.model_copy(update={"model": candidate.wire_model})
            stream = candidate.adapter.stream(stream_payload, candidate.creds, client).__aiter__()

            # Pull the first chunk before responding: this opens the upstream
            # connection and checks its status, so a failed start surfaces a real
            # HTTP error instead of a fake 200 empty stream.
            try:
                first = await stream.__anext__()
            except StopAsyncIteration:
                first = None
            except UpstreamStreamError as exc:
                breaker.record_failure(candidate.provider)
                return _error_response(
                    Failure(exc.status_code, "upstream error", exc.body, provider=candidate.provider)
                )
            except httpx.RequestError as exc:
                breaker.record_failure(candidate.provider)
                return _error_response(
                    Failure(502, f"upstream request failed: {exc}", provider=candidate.provider)
                )

            # Sniff the final usage chunk as the stream flows, then record real
            # tokens/cost once it finishes (the background task runs after that).
            usage_holder = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "content": ""}
            background.add_task(
                _record_stream_usage,
                request.app.state.session_factory,
                key,
                candidate.provider,
                candidate.model,
                usage_holder,
                started,
                getattr(request.state, "request_id", None),
                audit=settings.audit_capture_content,
                prompt=_latest_user_prompt(payload.messages),
                conversation_id=x_conversation_id,
                tags=tags,
            )
            handed_off = True
            return StreamingResponse(
                _metered_stream(first, stream, usage_holder, on_done=release),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        cache = request.app.state.cache
        key_str = cache_key(payload, key.tenant_id) if settings.cache_enabled else None

        if key_str is not None:
            cached = await cache.get(key_str)
            if cached is not None:
                logger.info("cache hit model=%s tenant=%s", payload.model, key.tenant_id)
                _record(request, background, key, resolve_provider(payload.model),
                        payload.model, cached, 200, cache_hit=True, started=started, tags=tags)
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
            deployments=deployments,
        )

        if isinstance(outcome, Success):
            body = outcome.candidate.adapter.parse_response(outcome.response.json()).model_dump(
                exclude_none=True
            )
            if key_str is not None:
                await cache.set(key_str, body, settings.cache_ttl_seconds)
            _record(request, background, key, outcome.candidate.provider,
                    outcome.candidate.model, body, 200, cache_hit=False, started=started, tags=tags)
            if settings.audit_capture_content:
                background.add_task(
                    write_audit,
                    request.app.state.session_factory,
                    trace_id=getattr(request.state, "request_id", None),
                    conversation_id=x_conversation_id,
                    key_id=key.key_id,
                    tenant_id=key.tenant_id,
                    provider=outcome.candidate.provider,
                    model=outcome.candidate.model,
                    prompt=_latest_user_prompt(payload.messages),
                    response=_response_text(body),
                )
            return JSONResponse(content=body, headers={"X-Cache": "MISS"})

        _record(request, background, key, candidates[0].provider, payload.model,
                None, outcome.status_code, cache_hit=False, started=started, tags=tags)
        return _error_response(outcome)
    finally:
        if not handed_off:
            release()


@router.post("/embeddings")
async def create_embeddings(
    payload: EmbeddingRequest,
    request: Request,
    background: BackgroundTasks,
    key: KeyContext = Depends(require_key),
    x_tags: Optional[str] = Header(default=None),
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
    if key.budget_exceeded():
        return _budget_exceeded(key)

    settings = get_settings()
    started = time.perf_counter()

    registry = request.app.state.model_registry
    model = registry.resolve_alias(payload.model)
    provider = resolve_provider(model)
    creds = creds_for_provider(provider, settings)
    if not creds.api_key:
        return _not_configured(provider)

    if settings.rate_limit_enabled:
        per_minute = key.rate_limit_per_minute or settings.rate_limit_per_minute
        rate, capacity = bucket_params(per_minute)
        limit = await request.app.state.rate_limiter.acquire(
            bucket_name(key.key_id, model), rate, capacity
        )
        if not limit.allowed:
            return _rate_limited(limit.retry_after)

    body = payload.model_dump()
    body["model"] = model
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        result = await ADAPTERS[provider].embed(model, body, creds, client)
    except EmbeddingsUnsupported:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"Provider '{provider}' does not support embeddings.",
                    "type": "embeddings_unsupported",
                }
            },
        )
    except UpstreamStreamError as exc:
        return _error_response(
            Failure(exc.status_code, "upstream error", exc.body, provider=provider)
        )
    except httpx.RequestError as exc:
        return _error_response(Failure(502, f"upstream request failed: {exc}", provider=provider))

    background.add_task(touch_last_used, request.app.state.session_factory, key.key_id)
    _record(request, background, key, provider, model, result, 200, cache_hit=False,
            started=started, tags=_merge_tags(key.tags, x_tags))
    return JSONResponse(content=result)


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
    tags: Optional[list[str]] = None,
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
        cost_usd=_maybe_cost(model, prompt, completion),
        latency_ms=int((time.perf_counter() - started) * 1000),
        status=status,
        cache_hit=cache_hit,
        trace_id=getattr(request.state, "request_id", None),
        tags=tags or [],
    )
    observe(event)
    background.add_task(record_usage, request.app.state.session_factory, event)


_UPSTREAM_FALLBACK_MESSAGE = {
    429: "The upstream provider is rate limiting requests. Try again shortly.",
    500: "The upstream provider returned an error.",
    502: "The upstream provider is unavailable.",
    503: "The upstream provider is temporarily unavailable.",
}
_MAX_ERROR_MESSAGE = 200


def _error_response(failure: Failure) -> JSONResponse:
    """Normalize any failure into a clean, typed error envelope.

    Upstream provider errors are condensed to a single short message (never the
    provider's raw, verbose body) and tagged so clients can tell a provider
    error apart from a gateway one.
    """
    if failure.body is not None:
        content = _normalize_upstream_error(failure.status_code, failure.provider, failure.body)
    else:
        content = {
            "error": {
                "message": failure.message,
                "type": _STATUS_ERROR_TYPES.get(failure.status_code, "upstream_error"),
            }
        }
    return JSONResponse(status_code=failure.status_code, content=content)


def _normalize_upstream_error(status: int, provider: str | None, raw: dict) -> dict:
    message = ""
    if isinstance(raw, dict) and isinstance(raw.get("error"), dict):
        message = (raw["error"].get("message") or "").strip()
    if not message:
        message = _UPSTREAM_FALLBACK_MESSAGE.get(status, "The upstream provider returned an error.")
    if len(message) > _MAX_ERROR_MESSAGE:
        message = message[: _MAX_ERROR_MESSAGE - 1].rstrip() + "…"

    error = {
        "message": message,
        "type": "upstream_rate_limit" if status == 429 else "upstream_error",
        "code": status,
    }
    if provider:
        error["provider"] = provider
    return {"error": error}


_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


def _not_configured(provider: str) -> JSONResponse:
    env = _PROVIDER_ENV.get(provider, f"{provider.upper()}_API_KEY")
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "message": f"Provider '{provider}' is not configured on this gateway (set {env}).",
                "type": "provider_not_configured",
            }
        },
    )


def _rate_limited(retry_after: float) -> JSONResponse:
    retry_seconds = max(1, math.ceil(retry_after))
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": f"Gateway rate limit exceeded. Retry after {retry_seconds}s.",
                "type": "rate_limit_exceeded",
            }
        },
        headers={"Retry-After": str(retry_seconds)},
    )


def _tpm_limited(limit: int, used: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": f"Token rate limit exceeded: {used} of {limit} tokens/min used.",
                "type": "token_rate_limit_exceeded",
            }
        },
        headers={"Retry-After": "60"},
    )


def _concurrency_limited(limit: Optional[int]) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": f"Concurrency limit reached ({limit} in-flight requests).",
                "type": "concurrency_limit_exceeded",
            }
        },
    )


def _budget_exceeded(key: KeyContext) -> JSONResponse:
    if key.token_budget is not None and key.tokens_used >= key.token_budget:
        message = f"Token budget exceeded: used {key.tokens_used} of {key.token_budget} tokens."
        period = key.budget_period
    elif key.cost_budget_usd is not None and key.cost_used >= key.cost_budget_usd:
        message = (
            f"Cost budget exceeded: used ${key.cost_used:.4f} of "
            f"${key.cost_budget_usd:.4f}."
        )
        period = key.budget_period
    elif key.team_token_budget is not None and key.team_tokens_used >= key.team_token_budget:
        message = (
            f"Team token budget exceeded: used {key.team_tokens_used} of "
            f"{key.team_token_budget} tokens."
        )
        period = key.team_budget_period
    else:
        message = (
            f"Team cost budget exceeded: used ${key.team_cost_used:.4f} of "
            f"${key.team_cost_budget_usd:.4f}."
        )
        period = key.team_budget_period
    if period != "total":
        message += f" (resets {period})"
    return JSONResponse(
        status_code=429,
        content={"error": {"message": message, "type": "budget_exceeded"}},
    )
