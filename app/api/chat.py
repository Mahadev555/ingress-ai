from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import get_settings

router = APIRouter()


@router.post("/chat/completions")
async def create_chat_completion(request: Request) -> Any:
    """OpenAI-compatible chat endpoint.

    Day 1 is a straight passthrough to OpenAI: we forward the request body,
    stream the response when asked, and relay the upstream status code. Later
    days add auth, routing, and multi-provider translation around this.
    """
    body = await request.json()

    settings = get_settings()
    client: httpx.AsyncClient = request.app.state.http_client
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    if body.get("stream"):
        return StreamingResponse(
            _stream_upstream(client, url, headers, body),
            media_type="text/event-stream",
        )

    try:
        upstream = await client.post(url, headers=headers, json=body)
    except httpx.RequestError as exc:
        return _bad_gateway(str(exc))

    return JSONResponse(status_code=upstream.status_code, content=upstream.json())


async def _stream_upstream(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> AsyncIterator[bytes]:
    """Relay the upstream SSE stream chunk-by-chunk without buffering it."""
    try:
        async with client.stream("POST", url, headers=headers, json=body) as upstream:
            async for chunk in upstream.aiter_raw():
                yield chunk
    except httpx.RequestError as exc:
        yield f'data: {{"error": {{"message": "upstream request failed: {exc}"}}}}\n\n'.encode()


def _bad_gateway(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"message": f"upstream request failed: {detail}", "type": "bad_gateway"}},
    )
