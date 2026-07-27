import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import admin, chat, mcp
from app.core.cache import create_cache
from app.core.concurrency import ConcurrencyLimiter
from app.core.config import get_settings
from app.core.model_registry import registry as model_registry
from app.core.ratelimit import create_rate_limiter
from app.db.seed import seed_credentials_if_empty, seed_models_if_empty
from app.db.session import create_engine, init_models
from app.mcp.registry import registry as mcp_registry
from app.observability.logging import configure_logging
from app.observability.metrics import render_latest
from app.router.deployments import registry as deployment_registry
from app.router.health import CircuitBreaker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared resources on startup, tear them down on shutdown.

    The HTTP client and database engine are created once and reused. State
    lives in the database, so any replica can serve any request.
    """
    settings = get_settings()
    configure_logging()

    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout)

    engine = create_engine(settings.database_url)
    await init_models(engine)
    app.state.db_engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Make the DB the source of truth: import the env model list and provider
    # keys on first run (both no-op once populated).
    await seed_models_if_empty(app.state.session_factory, settings)
    await seed_credentials_if_empty(app.state.session_factory, settings)

    await model_registry.reload(app.state.session_factory)
    app.state.model_registry = model_registry

    await deployment_registry.reload(app.state.session_factory)
    app.state.deployment_registry = deployment_registry

    await mcp_registry.reload(app.state.session_factory)
    app.state.mcp_registry = mcp_registry

    app.state.rate_limiter = create_rate_limiter(settings)
    app.state.circuit_breaker = CircuitBreaker(
        fail_threshold=settings.circuit_fail_threshold,
        reset_timeout=settings.circuit_reset_seconds,
    )
    app.state.cache = create_cache(settings)
    app.state.concurrency = ConcurrencyLimiter()

    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.rate_limiter.close()
        await app.state.cache.close()
        await engine.dispose()


app = FastAPI(title="Ingress AI Gateway", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign a trace/request id (honoring an inbound X-Request-ID) and echo it
    back on the response so a request can be correlated across logs and usage.
    Also rejects over-large request bodies (a cheap guardrail)."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id

    max_bytes = get_settings().max_request_bytes
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        return Response(
            content='{"error": {"message": "request body too large", "type": "payload_too_large"}}',
            status_code=413,
            media_type="application/json",
            headers={"X-Request-ID": request_id},
        )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(chat.router, prefix="/v1")
app.include_router(admin.router, prefix="/admin")
app.include_router(mcp.router, prefix="/mcp")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)
