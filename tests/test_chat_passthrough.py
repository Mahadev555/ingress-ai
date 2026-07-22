"""Day 1 deliverable: /v1/chat/completions proxies through to OpenAI.

The upstream is faked with httpx.MockTransport so the test needs no real API
key and makes no network calls. We assert the gateway forwards the request and
relays the response for both the JSON and streaming paths.
"""

import json

import httpx
from fastapi.testclient import TestClient

from app.main import app

COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hello from upstream"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_non_streaming_passthrough():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=COMPLETION)

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert resp.json() == COMPLETION
    # The gateway forwarded the request to the OpenAI endpoint unchanged.
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "gpt-4o-mini"


def test_streaming_passthrough():
    sse_body = (
        b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    async def stream_body():
        # An async generator keeps the response stream unconsumed, mirroring a
        # real upstream SSE response (bytes= would mark it already-read).
        yield sse_body

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=stream_body())

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert resp.status_code == 200
    assert resp.content == sse_body


def test_upstream_error_becomes_502():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "bad_gateway"


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
