from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import require_key
from app.core.auth import KeyContext
from app.core.config import get_settings
from app.providers.registry import resolve_model
from app.schemas.unified import ChatCompletionRequest

router = APIRouter()


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
    client: httpx.AsyncClient = request.app.state.http_client
    adapter, creds = resolve_model(payload.model, settings)

    if payload.stream:
        return StreamingResponse(
            adapter.stream(payload, creds, client),
            media_type="text/event-stream",
        )

    native = adapter.build_request(payload, creds)
    try:
        upstream = await client.request(
            native.method, native.url, headers=native.headers, json=native.json
        )
    except httpx.RequestError as exc:
        return _bad_gateway(str(exc))

    # Relay upstream errors (auth, rate limit, etc.) untouched so clients see
    # the provider's own error body and status.
    if upstream.status_code != 200:
        return JSONResponse(status_code=upstream.status_code, content=upstream.json())

    unified = adapter.parse_response(upstream.json())
    return JSONResponse(content=unified.model_dump(exclude_none=True))


def _bad_gateway(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"message": f"upstream request failed: {detail}", "type": "bad_gateway"}},
    )
