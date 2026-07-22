from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import admin, chat
from app.core.config import get_settings
from app.core.ratelimit import create_rate_limiter
from app.db.session import create_engine, init_models
from app.router.health import CircuitBreaker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared resources on startup, tear them down on shutdown.

    The HTTP client and database engine are created once and reused. State
    lives in the database, so any replica can serve any request.
    """
    settings = get_settings()

    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout)

    engine = create_engine(settings.database_url)
    await init_models(engine)
    app.state.db_engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app.state.rate_limiter = create_rate_limiter(settings)
    app.state.circuit_breaker = CircuitBreaker(
        fail_threshold=settings.circuit_fail_threshold,
        reset_timeout=settings.circuit_reset_seconds,
    )

    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.rate_limiter.close()
        await engine.dispose()


app = FastAPI(title="Ingress AI Gateway", lifespan=lifespan)

app.include_router(chat.router, prefix="/v1")
app.include_router(admin.router, prefix="/admin")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
