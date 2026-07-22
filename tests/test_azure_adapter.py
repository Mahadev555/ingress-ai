"""Azure OpenAI: deployment routing + api-version, OpenAI body/response reused."""

import httpx

from app.providers.azure_openai import AzureOpenAIAdapter
from app.providers.base import ProviderCreds
from app.schemas.unified import ChatCompletionRequest

CREDS = ProviderCreds(
    api_key="az-key",
    base_url="https://my-resource.openai.azure.com",
    extra={"api_version": "2024-02-15-preview"},
)

COMPLETION = {
    "id": "chatcmpl-az",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi from azure"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
}


def test_build_request_uses_deployment_and_api_version():
    req = ChatCompletionRequest(
        model="azure/my-deployment",
        messages=[{"role": "user", "content": "hi"}],
    )

    native = AzureOpenAIAdapter().build_request(req, CREDS)

    assert native.url == (
        "https://my-resource.openai.azure.com/openai/deployments/my-deployment"
        "/chat/completions?api-version=2024-02-15-preview"
    )
    assert native.headers["api-key"] == "az-key"
    # The azure/ prefix is stripped for the body's model / deployment name.
    assert native.json["model"] == "my-deployment"


def test_endpoint_routes_azure_by_prefix(make_gateway, monkeypatch):
    monkeypatch.setenv("AZURE_ENDPOINT", "https://my-resource.openai.azure.com")
    monkeypatch.setenv("AZURE_API_VERSION", "2024-02-15-preview")

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=COMPLETION)

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "azure/my-deployment",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert "/openai/deployments/my-deployment/chat/completions" in captured["url"]
    assert "api-version=2024-02-15-preview" in captured["url"]
    assert resp.json()["choices"][0]["message"]["content"] == "hi from azure"
