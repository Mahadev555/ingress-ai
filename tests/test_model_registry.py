"""DB model registry: listing, per-key filtering, and alias routing."""

import httpx

ADMIN = {"X-Admin-Token": "test-admin-token"}

CHAT_OK = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=CHAT_OK)


def test_registry_overrides_model_list(make_gateway):
    with make_gateway(_handler) as client:
        client.post("/admin/models", headers=ADMIN, json={"name": "house-model", "provider": "openai"})
        client.post(
            "/admin/models",
            headers=ADMIN,
            json={"name": "hidden-model", "provider": "openai", "enabled": False},
        )
        data = client.get("/v1/models").json()["data"]
        ids = {m["id"] for m in data}
    assert "house-model" in ids
    assert "hidden-model" not in ids  # disabled models are not advertised


def test_models_filtered_per_key(make_gateway):
    with make_gateway(_handler) as client:
        for name in ("model-a", "model-b"):
            client.post("/admin/models", headers=ADMIN, json={"name": name, "provider": "openai"})
        key = client.post(
            "/admin/keys", headers=ADMIN, json={"name": "scoped", "allowed_models": ["model-a"]}
        ).json()["key"]
        data = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"}).json()["data"]
        ids = {m["id"] for m in data}
    assert ids == {"model-a"}  # only the allowed model is visible to this key


def test_alias_routes_to_target_model(make_gateway):
    with make_gateway(_handler) as client:
        client.post(
            "/admin/models",
            headers=ADMIN,
            json={"name": "fast", "provider": "openai", "alias_of": "gpt-4o-mini"},
        )
        r = client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200
        recent = client.get("/admin/usage/recent", headers=ADMIN).json()
    # Usage is recorded against the resolved target model, not the alias.
    assert recent[0]["model"] == "gpt-4o-mini"
