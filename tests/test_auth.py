"""Virtual keys gate the gateway; provider keys stay server-side."""

import httpx
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_TOKEN

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

CHAT_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


def _echo_completion(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=COMPLETION)


def test_missing_key_is_rejected(make_gateway):
    with make_gateway(_echo_completion) as client:
        # Drop the auth header the fixture set.
        client.headers.pop("Authorization", None)
        resp = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["type"] == "auth_error"


def test_invalid_key_is_rejected(make_gateway):
    with make_gateway(_echo_completion) as client:
        client.headers["Authorization"] = "Bearer sk-ingress-not-a-real-key"
        resp = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert resp.status_code == 401


def test_valid_key_allows_request(make_gateway):
    with make_gateway(_echo_completion) as client:
        resp = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "ok"


def test_allowed_models_restriction_returns_403(make_gateway):
    with make_gateway(_echo_completion, allowed_models=["gpt-4o-mini"]) as client:
        ok = client.post("/v1/chat/completions", json=CHAT_BODY)
        denied = client.post(
            "/v1/chat/completions",
            json={"model": "claude-3-5-sonnet", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert ok.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"]["type"] == "model_not_allowed"


def test_admin_requires_token(make_gateway):
    with make_gateway() as client:
        # No X-Admin-Token header.
        resp = client.post("/admin/keys", json={"name": "x"})

    assert resp.status_code == 401


def test_created_key_is_hashed_not_stored_plaintext(make_gateway):
    with make_gateway() as client:
        created = client.post(
            "/admin/keys",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"name": "prod"},
        )
        listed = client.get("/admin/keys", headers={"X-Admin-Token": ADMIN_TOKEN})

    full_key = created.json()["key"]
    assert full_key.startswith("sk-ingress-")

    # The listing exposes only the prefix/hash-free metadata, never a full key.
    keys = listed.json()
    prod = next(k for k in keys if k["name"] == "prod")
    assert prod["key_prefix"] in full_key
    for k in keys:
        assert "key" not in k
        assert "key_hash" not in k


def test_admin_disabled_without_api_key(monkeypatch):
    # No ADMIN_API_KEY configured -> admin surface is closed. Force it empty so
    # the test doesn't depend on a developer's local .env.
    monkeypatch.setenv("ADMIN_API_KEY", "")
    with TestClient(app) as client:
        resp = client.post("/admin/keys", json={"name": "x"})
    assert resp.status_code == 503
