"""The adapter contract: unified request -> native request -> unified response."""

from app.providers.base import ProviderCreds
from app.providers.openai import OpenAIAdapter
from app.schemas.unified import ChatCompletionRequest

CREDS = ProviderCreds(api_key="sk-test", base_url="https://api.openai.com/v1")


def test_build_request_targets_openai_and_carries_creds():
    adapter = OpenAIAdapter()
    req = ChatCompletionRequest(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
    )

    native = adapter.build_request(req, CREDS)

    assert native.method == "POST"
    assert native.url == "https://api.openai.com/v1/chat/completions"
    assert native.headers["Authorization"] == "Bearer sk-test"
    assert native.json["model"] == "gpt-4o-mini"
    assert native.json["temperature"] == 0.2
    # exclude_none keeps unset optional params out of the wire body.
    assert "max_tokens" not in native.json


def test_extra_openai_fields_pass_through():
    adapter = OpenAIAdapter()
    req = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object"},
        }
    )

    native = adapter.build_request(req, CREDS)

    assert native.json["response_format"] == {"type": "json_object"}


def test_parse_response_returns_unified_model():
    adapter = OpenAIAdapter()
    payload = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    unified = adapter.parse_response(payload)

    assert unified.id == "chatcmpl-1"
    assert unified.choices[0].message.content == "ok"
    assert unified.usage.total_tokens == 2
