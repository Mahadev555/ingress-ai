"""Gemini is the divergent adapter: prove the unified schema survives the trip."""

import json

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import ProviderCreds
from app.providers.gemini import GeminiAdapter
from app.schemas.unified import ChatCompletionRequest

CREDS = ProviderCreds(api_key="g-key", base_url="https://gen.googleapis.com/v1beta")

GEMINI_PAYLOAD = {
    "candidates": [
        {
            "content": {"parts": [{"text": "hello from gemini"}], "role": "model"},
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 4,
        "candidatesTokenCount": 3,
        "totalTokenCount": 7,
    },
    "modelVersion": "gemini-1.5-flash",
}


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_build_request_translates_to_gemini_shape():
    adapter = GeminiAdapter()
    req = ChatCompletionRequest(
        model="gemini-1.5-flash",
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey"},
        ],
        temperature=0.5,
        max_tokens=256,
        top_p=0.9,
    )

    native = adapter.build_request(req, CREDS)

    assert native.url.startswith(
        "https://gen.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?"
    )
    assert "key=g-key" in native.url
    # System message is pulled out; roles are remapped (assistant -> model).
    assert native.json["systemInstruction"]["parts"][0]["text"] == "be terse"
    assert [c["role"] for c in native.json["contents"]] == ["user", "model"]
    assert native.json["contents"][0]["parts"][0]["text"] == "hi"
    # Generation params are nested and renamed.
    gen = native.json["generationConfig"]
    assert gen == {"temperature": 0.5, "maxOutputTokens": 256, "topP": 0.9}


def test_parse_response_maps_to_unified():
    unified = GeminiAdapter().parse_response(GEMINI_PAYLOAD)

    assert unified.choices[0].message.role == "assistant"
    assert unified.choices[0].message.content == "hello from gemini"
    assert unified.choices[0].finish_reason == "stop"
    assert unified.usage.prompt_tokens == 4
    assert unified.usage.completion_tokens == 3
    assert unified.usage.total_tokens == 7


def test_endpoint_routes_gemini_by_model_name():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=GEMINI_PAYLOAD)

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    # Routed to Gemini's native endpoint...
    assert ":generateContent" in captured["url"]
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "hi"
    # ...but the client sees a normalized OpenAI-shaped response.
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "hello from gemini"
    assert body["usage"]["total_tokens"] == 7


def test_gemini_streaming_normalizes_to_openai_chunks():
    async def sse_body():
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"hel"}]}}]}\n\n'
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"lo"}],"role":"model"},"finishReason":"STOP"}]}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert ":streamGenerateContent" in str(request.url)
        assert "alt=sse" in str(request.url)
        return httpx.Response(200, content=sse_body())

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-1.5-flash",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    text = resp.text
    assert '"object": "chat.completion.chunk"' in text
    assert '"content": "hel"' in text
    assert '"content": "lo"' in text
    assert '"finish_reason": "stop"' in text
    assert text.rstrip().endswith("data: [DONE]")
