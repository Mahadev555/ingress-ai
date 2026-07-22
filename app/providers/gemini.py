import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from app.providers.base import NativeRequest, ProviderAdapter, ProviderCreds
from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse, Message

# Gemini uses SCREAMING_SNAKE finish reasons; map them to OpenAI's vocabulary.
_FINISH_REASONS = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
}


class GeminiAdapter(ProviderAdapter):
    """Google AI Studio (generateContent). The most divergent adapter: roles,
    message shape, system prompt, generation params and usage all differ."""

    def build_request(self, req: ChatCompletionRequest, creds: ProviderCreds) -> NativeRequest:
        return self._native(req, creds, streaming=False)

    def parse_response(self, payload: dict[str, Any]) -> ChatCompletionResponse:
        choices = []
        for i, candidate in enumerate(payload.get("candidates", [])):
            text = _join_parts(candidate.get("content", {}).get("parts", []))
            choices.append(
                {
                    "index": candidate.get("index", i),
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": _finish_reason(candidate.get("finishReason")),
                }
            )

        meta = payload.get("usageMetadata", {})
        usage = {
            "prompt_tokens": meta.get("promptTokenCount", 0),
            "completion_tokens": meta.get("candidatesTokenCount", 0),
            "total_tokens": meta.get("totalTokenCount", 0),
        }

        return ChatCompletionResponse.model_validate(
            {
                "id": payload.get("responseId") or _new_id(),
                "created": int(time.time()),
                "model": payload.get("modelVersion", "gemini"),
                "choices": choices,
                "usage": usage,
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

        async with client.stream(
            native.method, native.url, headers=native.headers, json=native.json
        ) as upstream:
            async for line in upstream.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data:
                    continue

                gemini_chunk = json.loads(data)
                candidate = (gemini_chunk.get("candidates") or [{}])[0]
                text = _join_parts(candidate.get("content", {}).get("parts", []))
                openai_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": gemini_chunk.get("modelVersion", req.model),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": _finish_reason(candidate.get("finishReason")),
                        }
                    ],
                }
                yield f"data: {json.dumps(openai_chunk)}\n\n".encode()

        yield b"data: [DONE]\n\n"

    def _native(
        self, req: ChatCompletionRequest, creds: ProviderCreds, streaming: bool
    ) -> NativeRequest:
        contents, system = _to_contents(req.messages)

        body: dict[str, Any] = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        generation_config = _generation_config(req)
        if generation_config:
            body["generationConfig"] = generation_config

        method_name = "streamGenerateContent" if streaming else "generateContent"
        query = f"key={creds.api_key}"
        if streaming:
            query = f"alt=sse&{query}"
        url = f"{creds.base_url}/models/{req.model}:{method_name}?{query}"

        return NativeRequest(
            method="POST",
            url=url,
            headers={"Content-Type": "application/json"},
            json=body,
        )


def _to_contents(messages: list[Message]) -> tuple[list[dict[str, Any]], str]:
    """Split OpenAI-style messages into Gemini `contents` + a system string.

    Roles are remapped (`assistant` -> `model`); system messages are pulled out
    into a single `systemInstruction`, which is a top-level field in Gemini.
    """
    contents: list[dict[str, Any]] = []
    system_parts: list[str] = []

    for message in messages:
        text = _content_text(message.content)
        if message.role == "system":
            system_parts.append(text)
            continue
        role = "model" if message.role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": text}]})

    return contents, "\n".join(system_parts)


def _generation_config(req: ChatCompletionRequest) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if req.temperature is not None:
        config["temperature"] = req.temperature
    if req.max_tokens is not None:
        config["maxOutputTokens"] = req.max_tokens
    if req.top_p is not None:
        config["topP"] = req.top_p
    return config


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # OpenAI multimodal content: keep the text parts.
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _join_parts(parts: list[dict[str, Any]]) -> str:
    return "".join(part.get("text", "") for part in parts)


def _finish_reason(reason: Any) -> str | None:
    if not reason:
        return None
    return _FINISH_REASONS.get(reason, "stop")


def _new_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"
