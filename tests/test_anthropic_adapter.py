"""Anthropic /v1/messages translation and end-to-end routing by model name."""

import json

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ProviderCreds
from app.schemas.unified import ChatCompletionRequest

CREDS = ProviderCreds(
    api_key="sk-ant-x",
    base_url="https://api.anthropic.com",
    extra={"version": "2023-06-01"},
)

ANTHROPIC_PAYLOAD = {
    "id": "msg_123",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet",
    "content": [{"type": "text", "text": "hi from claude"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 6, "output_tokens": 4},
}


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_build_request_lifts_system_and_sets_max_tokens():
    req = ChatCompletionRequest(
        model="claude-3-5-sonnet",
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
    )

    native = AnthropicAdapter().build_request(req, CREDS)

    assert native.url == "https://api.anthropic.com/v1/messages"
    assert native.headers["x-api-key"] == "sk-ant-x"
    assert native.headers["anthropic-version"] == "2023-06-01"
    # System is a top-level field, not a message.
    assert native.json["system"] == "be terse"
    assert native.json["messages"] == [{"role": "user", "content": "hi"}]
    # max_tokens is required by Anthropic; a default is supplied.
    assert native.json["max_tokens"] == 1024


def test_parse_response_maps_to_unified():
    unified = AnthropicAdapter().parse_response(ANTHROPIC_PAYLOAD)

    assert unified.choices[0].message.content == "hi from claude"
    assert unified.choices[0].finish_reason == "stop"
    assert unified.usage.prompt_tokens == 6
    assert unified.usage.completion_tokens == 4
    assert unified.usage.total_tokens == 10


def test_endpoint_routes_claude_by_model_name():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=ANTHROPIC_PAYLOAD)

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-3-5-sonnet",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert captured["url"].endswith("/v1/messages")
    assert resp.json()["choices"][0]["message"]["content"] == "hi from claude"


def test_anthropic_streaming_normalizes_to_openai_chunks():
    async def sse_body():
        yield b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hel"}}\n\n'
        yield b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}\n\n'
        yield b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=sse_body())

    with TestClient(app) as client:
        app.state.http_client = _mock_client(handler)
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-3-5-sonnet",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    text = resp.text
    assert '"content": "hel"' in text
    assert '"content": "lo"' in text
    assert '"finish_reason": "stop"' in text
    assert text.rstrip().endswith("data: [DONE]")
