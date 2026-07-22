from typing import Any, AsyncIterator

import httpx

from app.providers.base import NativeRequest, ProviderAdapter, ProviderCreds
from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse


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
            json=req.model_dump(exclude_none=True),
        )

    def parse_response(self, payload: dict[str, Any]) -> ChatCompletionResponse:
        return ChatCompletionResponse.model_validate(payload)

    async def stream(
        self,
        req: ChatCompletionRequest,
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[bytes]:
        native = self.build_request(req, creds)
        native.json["stream"] = True
        async with client.stream(
            native.method, native.url, headers=native.headers, json=native.json
        ) as upstream:
            async for chunk in upstream.aiter_raw():
                yield chunk
