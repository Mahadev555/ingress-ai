"""Per-key rate limits and the PATCH edit-key endpoint."""

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


def _mint(client, **body):
    r = client.post("/admin/keys", headers=ADMIN, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_key_accepts_rate_limit(make_gateway):
    with make_gateway(_handler) as client:
        key = _mint(client, name="n", rate_limit_per_minute=42)
        assert key["rate_limit_per_minute"] == 42


def test_patch_key_updates_fields(make_gateway):
    with make_gateway(_handler) as client:
        kid = _mint(client, name="a")["id"]
        r = client.patch(
            f"/admin/keys/{kid}",
            headers=ADMIN,
            json={"name": "b", "rate_limit_per_minute": 10, "allowed_models": ["gpt-4o-mini"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "b"
        assert body["rate_limit_per_minute"] == 10
        assert body["allowed_models"] == ["gpt-4o-mini"]


def test_patch_can_clear_budget(make_gateway):
    with make_gateway(_handler) as client:
        kid = _mint(client, name="a", token_budget=100)["id"]
        r = client.patch(f"/admin/keys/{kid}", headers=ADMIN, json={"token_budget": None})
        assert r.status_code == 200
        assert r.json()["token_budget"] is None


def test_patch_missing_key_is_404(make_gateway):
    with make_gateway(_handler) as client:
        r = client.patch("/admin/keys/9999", headers=ADMIN, json={"name": "x"})
        assert r.status_code == 404


def test_expired_key_is_rejected(make_gateway):
    with make_gateway(_handler) as client:
        key = _mint(client, name="old", expires_at="2000-01-01T00:00:00Z")["key"]
        r = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["type"] == "key_expired"


def test_tpm_limit_is_enforced(make_gateway):
    with make_gateway(_handler) as client:
        key = _mint(client, name="tpm", tpm_limit=1)["key"]
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
        first = client.post("/v1/chat/completions", headers=headers, json=payload)
        second = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "token_rate_limit_exceeded"


def test_cost_budget_is_enforced(make_gateway):
    with make_gateway(_handler) as client:
        key = _mint(client, name="cost", cost_budget_usd=1e-7)["key"]
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
        first = client.post("/v1/chat/completions", headers=headers, json=payload)
        second = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "budget_exceeded"


def test_per_key_rate_limit_is_enforced(make_gateway):
    # A key capped at 1/min: first request passes, the second is rate limited —
    # independent of the global default (60/min).
    with make_gateway(_handler) as client:
        key = _mint(client, name="rl", rate_limit_per_minute=1)["key"]
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}

        first = client.post("/v1/chat/completions", headers=headers, json=payload)
        second = client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "rate_limit_exceeded"
