"""Multi-deployment routing + load balancing (feature ①)."""

import httpx

from app.router.deployments import Deployment, DeploymentRegistry

ADMIN = {"X-Admin-Token": "test-admin-token"}

CHAT_OK = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
}


def _chat(client, model="gpt-4o-mini"):
    return client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
    )


def _new_credential(client, api_key="k", provider="openai", name=None):
    """Create a provider credential (where the key lives) and return its id."""
    r = client.post(
        "/admin/providers",
        headers=ADMIN,
        json={"name": name or f"{provider}-{api_key}", "provider": provider, "api_key": api_key},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _deployment(**over):
    base = dict(id=1, model_name="m", provider="openai", api_key="k", base_url=None, weight=1, enabled=True)
    base.update(over)
    return Deployment(**base)


def test_registry_orders_least_busy():
    reg = DeploymentRegistry()
    reg.set([_deployment(id=1), _deployment(id=2)])
    reg.note_start(1)
    reg.note_start(1)  # deployment 1 has two in-flight
    order = reg.ordered("m", "least-busy")
    assert order[0].id == 2  # the idle one is preferred


def test_registry_latency_prefers_faster():
    reg = DeploymentRegistry()
    reg.set([_deployment(id=1), _deployment(id=2)])
    reg.note_end(1, 500.0, ok=True)
    reg.note_end(2, 50.0, ok=True)
    order = reg.ordered("m", "latency")
    assert order[0].id == 2  # lower latency first


def test_registry_falls_back_to_env_when_empty():
    reg = DeploymentRegistry()
    assert reg.has("gpt-4o-mini") is False  # no deployments → env credential path


def test_deployment_uses_its_credential_key(make_gateway):
    """A deployment routes through its credential's key, not the env default."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=CHAT_OK)

    with make_gateway(handler) as client:
        cid = _new_credential(client, api_key="dep-secret-key", name="openai-dep")
        created = client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "gpt-4o-mini", "credential_id": cid},
        )
        assert created.status_code == 200, created.text
        assert "dep-secret-key" not in created.text  # secret never returned
        assert _chat(client).status_code == 200

    assert seen["auth"] == "Bearer dep-secret-key"


def test_env_models_are_seeded_into_db(make_gateway):
    """The AVAILABLE_MODELS env list is imported into the DB registry on start,
    so the registry is the source of truth (not the env list at request time)."""
    with make_gateway() as client:
        models = client.get("/admin/models", headers=ADMIN).json()
    names = {m["name"] for m in models}
    assert "gpt-4o-mini" in names  # seeded from the default env list
    # No hardcoded prices: seeded models start with no price (add it if wanted).
    mini = next(m for m in models if m["name"] == "gpt-4o-mini")
    assert mini["input_price_per_1m"] is None


def test_deployment_requires_registered_model(make_gateway):
    with make_gateway() as client:
        cid = _new_credential(client)
        r = client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "no-such-model", "credential_id": cid},
        )
    assert r.status_code == 400  # must point at a registered model


def test_cannot_delete_model_with_deployments(make_gateway):
    with make_gateway() as client:
        cid = _new_credential(client)
        models = client.get("/admin/models", headers=ADMIN).json()
        mini = next(m for m in models if m["name"] == "gpt-4o-mini")
        client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "gpt-4o-mini", "credential_id": cid},
        )
        blocked = client.delete(f"/admin/models/{mini['id']}", headers=ADMIN)
        # The model now reports its backing deployment count.
        refreshed = client.get("/admin/models", headers=ADMIN).json()
    assert blocked.status_code == 409
    assert next(m for m in refreshed if m["name"] == "gpt-4o-mini")["deployment_count"] == 1


def test_upstream_model_override_routes_to_azure_deployment(make_gateway):
    """One public model can fan out to differently-named Azure deployments via
    the per-deployment upstream_model override (used in the URL path)."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=CHAT_OK)

    with make_gateway(handler) as client:
        client.post("/admin/models", headers=ADMIN, json={"name": "azure/gpt-4o", "provider": "azure"})
        cid = client.post(
            "/admin/providers",
            headers=ADMIN,
            json={"name": "az", "provider": "azure", "api_key": "k",
                  "base_url": "https://x.openai.azure.com"},
        ).json()["id"]
        created = client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "azure/gpt-4o", "credential_id": cid, "upstream_model": "gpt-4o-1"},
        )
        assert created.status_code == 200, created.text
        assert created.json()["upstream_model"] == "gpt-4o-1"

        r = client.post(
            "/v1/chat/completions",
            json={"model": "azure/gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200
        # Usage is recorded under the public model name, not the deployment name.
        recent = client.get("/admin/usage/recent", headers=ADMIN).json()

    assert "/deployments/gpt-4o-1/" in seen["path"]  # routed to the override
    assert recent[0]["model"] == "azure/gpt-4o"  # accounted under the public name


def test_failover_across_credential_keys(make_gateway):
    """One credential's key fails; the request fails over to the other."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "bad-key" in request.headers.get("authorization", ""):
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, json=CHAT_OK)

    with make_gateway(handler) as client:
        for api_key in ("bad-key", "good-key"):
            cid = _new_credential(client, api_key=api_key, name=f"openai-{api_key}")
            r = client.post(
                "/admin/deployments",
                headers=ADMIN,
                json={"model_name": "gpt-4o-mini", "credential_id": cid},
            )
            assert r.status_code == 200
        # Regardless of shuffle order, a failing key fails over to the healthy one.
        assert _chat(client).status_code == 200
