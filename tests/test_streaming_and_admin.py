"""Day 10: SSE hardening and admin key CRUD (revoke)."""

import httpx

from tests.conftest import ADMIN_TOKEN

CHAT_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
STREAM_BODY = {**CHAT_BODY, "stream": True}

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def test_streaming_sets_anti_buffering_headers(make_gateway):
    sse = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'

    async def body():
        yield sse

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    with make_gateway(handler) as client:
        resp = client.post("/v1/chat/completions", json=STREAM_BODY)

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    assert resp.content == sse


def test_stream_start_connection_failure_returns_error(make_gateway):
    # A connection failure when opening the stream surfaces a real HTTP error,
    # not a fake 200 empty stream.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with make_gateway(handler) as client:
        resp = client.post("/v1/chat/completions", json=STREAM_BODY)

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "bad_gateway"


def test_stream_upstream_error_status_is_surfaced(make_gateway):
    # Provider returns 429 (e.g. rate limited) when opening the stream — the
    # client must see 429 with a normalized upstream error type, not a 200.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with make_gateway(handler) as client:
        resp = client.post("/v1/chat/completions", json=STREAM_BODY)

    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["type"] == "upstream_rate_limit"  # provider, not gateway
    assert body["error"]["provider"] == "openai"


def test_streaming_meters_usage(make_gateway):
    # A real provider ends the stream with a usage chunk; the gateway records it.
    async def body():
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield b'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":5,"total_tokens":12}}\n\n'
        yield b"data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    with make_gateway(handler) as client:
        resp = client.post("/v1/chat/completions", json=STREAM_BODY)
        assert resp.status_code == 200
        summary = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 12  # metered from the streamed usage chunk


def test_revoked_key_is_rejected(make_gateway):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=COMPLETION)

    with make_gateway(handler) as client:
        created = client.post(
            "/admin/keys",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"name": "temp"},
        ).json()
        client.headers["Authorization"] = f"Bearer {created['key']}"

        before = client.post("/v1/chat/completions", json=CHAT_BODY)

        revoke = client.delete(
            f"/admin/keys/{created['id']}", headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        after = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert before.status_code == 200
    assert revoke.status_code == 204
    assert after.status_code == 401  # revoked key no longer authenticates


def test_revoke_unknown_key_returns_404(make_gateway):
    with make_gateway() as client:
        resp = client.delete("/admin/keys/9999", headers={"X-Admin-Token": ADMIN_TOKEN})
    assert resp.status_code == 404
