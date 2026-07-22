from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api import chat
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared resources on startup, tear them down on shutdown.

    The HTTP client is created once and reused for every upstream call, so we
    keep a warm connection pool instead of opening a socket per request.
    """
    settings = get_settings()
    app.state.http_client = httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Ingress AI Gateway", lifespan=lifespan)

app.include_router(chat.router, prefix="/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
