import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from app.providers.base import (
    NativeRequest,
    ProviderAdapter,
    ProviderCreds,
    UpstreamStreamError,
    read_stream_error,
)
from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse, Message

# Anthropic's max_tokens is required; fall back to this when a client omits it.
_DEFAULT_MAX_TOKENS = 1024

_STOP_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


class AnthropicAdapter(ProviderAdapter):
    """Anthropic /v1/messages: top-level `system`, content as text blocks."""

    def build_request(self, req: ChatCompletionRequest, creds: ProviderCreds) -> NativeRequest:
        return self._native(req, creds, streaming=False)

    def parse_response(self, payload: dict[str, Any]) -> ChatCompletionResponse:
        text = _join_text_blocks(payload.get("content", []))
        usage = payload.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return ChatCompletionResponse.model_validate(
            {
                "id": payload.get("id") or _new_id(),
                "created": int(time.time()),
                "model": payload.get("model", "claude"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": _stop_reason(payload.get("stop_reason")),
                    }
                ],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            }
        )

    async def stream(
        self,
        req: ChatCompletionRequest,
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[bytes]:
        native = self._native(req, creds, streaming=True)
        chunk_id = _new_id()
        created = int(time.time())

        def envelope(delta: dict[str, Any], finish: str | None) -> bytes:
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": req.model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(chunk)}\n\n".encode()

        input_tokens = 0
        output_tokens = 0

        async with client.stream(
            native.method, native.url, headers=native.headers, json=native.json
        ) as upstream:
            if upstream.status_code != 200:
                raise UpstreamStreamError(upstream.status_code, await read_stream_error(upstream))
            async for line in upstream.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:") :].strip())
                event_type = event.get("type")

                if event_type == "message_start":
                    input_tokens = (
                        event.get("message", {}).get("usage", {}).get("input_tokens", 0)
                    )
                elif event_type == "content_block_delta":
                    text = event.get("delta", {}).get("text", "")
                    if text:
                        yield envelope({"content": text}, None)
                elif event_type == "message_delta":
                    output_tokens = event.get("usage", {}).get("output_tokens", output_tokens)
                    finish = _stop_reason(event.get("delta", {}).get("stop_reason"))
                    if finish:
                        yield envelope({}, finish)

        if input_tokens or output_tokens:
            final = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": req.model,
                "choices": [],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            }
            yield f"data: {json.dumps(final)}\n\n".encode()

        yield b"data: [DONE]\n\n"

    def _native(
        self, req: ChatCompletionRequest, creds: ProviderCreds, streaming: bool
    ) -> NativeRequest:
        system, messages = _split_system(req.messages)

        body: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
            "max_tokens": req.max_tokens or _DEFAULT_MAX_TOKENS,
        }
        if system:
            body["system"] = system
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.top_p is not None:
            body["top_p"] = req.top_p
        if streaming:
            body["stream"] = True

        return NativeRequest(
            method="POST",
            url=f"{creds.base_url}/v1/messages",
            headers={
                "x-api-key": creds.api_key,
                "anthropic-version": creds.extra.get("version", ""),
                "Content-Type": "application/json",
            },
            json=body,
        )


def _split_system(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Pull system messages into a top-level string; keep the rest as-is."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for message in messages:
        if message.role == "system":
            system_parts.append(_content_text(message.content))
            continue
        converted.append({"role": message.role, "content": _content_text(message.content)})

    return "\n".join(system_parts), converted


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _join_text_blocks(blocks: list[dict[str, Any]]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _stop_reason(reason: Any) -> str | None:
    if not reason:
        return None
    return _STOP_REASONS.get(reason, "stop")


def _new_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"
