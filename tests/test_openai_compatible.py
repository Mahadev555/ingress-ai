"""OpenAI-compatible providers (Groq, Together, DeepSeek, OpenRouter, Ollama).

They share OpenAI's wire format, so the OpenAI adapter routes them by base_url;
the model's provider comes from the DB registry (their names aren't prefixable)."""

import httpx

from app.core.config import get_settings
from app.core.model_registry import RegisteredModel, registry

ADMIN = {"X-Admin-Token": "test-admin-token"}

CHAT_OK = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "x",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _chat(client, model):
    return client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
    )


def test_config_lists_compatible_providers(make_gateway):
    with make_gateway() as client:
        providers = client.get("/v1/config").json()["providers"]
    for p in ("openai", "anthropic", "gemini", "azure",
              "groq", "together", "deepseek", "openrouter", "ollama"):
        assert p in providers


def test_resolve_provider_prefers_registry_over_prefix():
    registry.set([
        RegisteredModel(
            name="deepseek-chat", provider="deepseek", alias_of=None,
            input_price_per_1m=None, output_price_per_1m=None,
            default_rate_limit_per_minute=None, default_tpm_limit=None, enabled=True,
        )
    ])
    try:
        from app.providers.registry import resolve_provider
        assert resolve_provider("deepseek-chat") == "deepseek"  # registry wins
        assert resolve_provider("claude-3-5-sonnet") == "anthropic"  # prefix fallback
        assert resolve_provider("mystery") == "openai"  # default fallback
    finally:
        registry.set([])


def test_groq_model_routes_to_groq_via_env(make_gateway, monkeypatch):
    """Register a Groq model + set GROQ_API_KEY → routes to the Groq endpoint."""
    monkeypatch.setenv("GROQ_API_KEY", "gk-test")
    get_settings.cache_clear()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=CHAT_OK)

    with make_gateway(handler) as client:
        client.post("/admin/models", headers=ADMIN,
                    json={"name": "llama-3.1-8b-instant", "provider": "groq"})
        assert _chat(client, "llama-3.1-8b-instant").status_code == 200

    assert "api.groq.com" in seen["url"]
    assert seen["auth"] == "Bearer gk-test"


def test_deepseek_routes_via_credential_and_deployment(make_gateway):
    """No env key needed: a DeepSeek credential + deployment routes there."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=CHAT_OK)

    with make_gateway(handler) as client:
        client.post("/admin/models", headers=ADMIN,
                    json={"name": "deepseek-chat", "provider": "deepseek"})
        cid = client.post("/admin/providers", headers=ADMIN,
                          json={"name": "ds", "provider": "deepseek", "api_key": "dk"}).json()["id"]
        client.post("/admin/deployments", headers=ADMIN,
                    json={"model_name": "deepseek-chat", "credential_id": cid})
        assert _chat(client, "deepseek-chat").status_code == 200

    assert "api.deepseek.com" in seen["url"]
