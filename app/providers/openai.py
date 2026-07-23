from typing import Any, AsyncIterator, Optional

import httpx

from app.providers.base import (
    NativeRequest,
    ProviderAdapter,
    ProviderCreds,
    UpstreamStreamError,
    read_stream_error,
)
from app.schemas.unified import GATEWAY_ONLY_FIELDS, ChatCompletionRequest, ChatCompletionResponse


def _safe_json(resp: httpx.Response) -> Optional[dict]:
    try:
        return resp.json()
    except Exception:
        return None


class OpenAIAdapter(ProviderAdapter):
    """OpenAI is the canonical shape, so this adapter is a near-passthrough."""

    def build_request(self, req: ChatCompletionRequest, creds: ProviderCreds) -> NativeRequest:
        return NativeRequest(
            method="POST",
            url=f"{creds.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {creds.api_key}",
                "Content-Type": "application/json",
            },
            json=req.model_dump(exclude_none=True, exclude=GATEWAY_ONLY_FIELDS),
        )

    def parse_response(self, payload: dict[str, Any]) -> ChatCompletionResponse:
        return ChatCompletionResponse.model_validate(payload)

    async def embed(
        self,
        model: str,
        payload: dict[str, Any],
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        resp = await client.post(
            f"{creds.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {creds.api_key}",
                "Content-Type": "application/json",
            },
            json={**payload, "model": model},
        )
        if resp.status_code != 200:
            raise UpstreamStreamError(resp.status_code, _safe_json(resp))
        return resp.json()

    async def stream(
        self,
        req: ChatCompletionRequest,
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[bytes]:
        native = self.build_request(req, creds)
        native.json["stream"] = True
        # Ask the provider to include a final usage chunk so the gateway can
        # meter streamed requests (tokens/cost).
        native.json["stream_options"] = {"include_usage": True}
        async with client.stream(
            native.method, native.url, headers=native.headers, json=native.json
        ) as upstream:
            if upstream.status_code != 200:
                raise UpstreamStreamError(upstream.status_code, await read_stream_error(upstream))
            async for chunk in upstream.aiter_raw():
                yield chunk
