"""Provider credentials: where keys live — seeded from env, masked, encrypted."""

import httpx

from app.core import secrets
from app.core.config import get_settings

ADMIN = {"X-Admin-Token": "test-admin-token"}


def test_credentials_seeded_from_env(make_gateway):
    with make_gateway() as client:
        creds = client.get("/admin/providers", headers=ADMIN).json()
    names = {c["name"] for c in creds}
    # conftest sets all four provider env keys, so each seeds a credential.
    assert {"openai-env", "anthropic-env", "gemini-env", "azure-env"} <= names
    assert all(c["has_api_key"] for c in creds)


def test_credential_key_is_never_returned(make_gateway):
    with make_gateway() as client:
        r = client.post(
            "/admin/providers",
            headers=ADMIN,
            json={"name": "openai-x", "provider": "openai", "api_key": "sk-super-secret"},
        )
        body = r.json()
        listed = client.get("/admin/providers", headers=ADMIN).text
    assert r.status_code == 200
    assert body["has_api_key"] is True
    assert "sk-super-secret" not in r.text  # not in the create response
    assert "sk-super-secret" not in listed  # not in the listing


def test_delete_credential_in_use_is_blocked(make_gateway):
    with make_gateway() as client:
        cid = client.post(
            "/admin/providers",
            headers=ADMIN,
            json={"name": "openai-u", "provider": "openai", "api_key": "k"},
        ).json()["id"]
        client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "gpt-4o-mini", "credential_id": cid},
        )
        blocked = client.delete(f"/admin/providers/{cid}", headers=ADMIN)
    assert blocked.status_code == 409  # a deployment still references it


# --- encryption at rest ------------------------------------------------------


def test_secret_round_trips_when_key_set(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "test-passphrase")
    get_settings.cache_clear()
    token = secrets.encrypt("sk-abc123")
    assert token != "sk-abc123"
    assert token.startswith("enc:")
    assert secrets.decrypt(token) == "sk-abc123"


def test_secret_is_plaintext_without_key(monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    assert secrets.encrypt("sk-abc123") == "sk-abc123"  # dev default
    assert secrets.decrypt("sk-abc123") == "sk-abc123"  # plaintext passes through


def test_encrypted_credential_decrypts_for_routing(make_gateway, monkeypatch):
    """With encryption on, the stored key is ciphertext but routing still uses
    the real key (decrypted in-process)."""
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "test-passphrase")
    get_settings.cache_clear()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "id": "x", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    with make_gateway(handler) as client:
        cid = client.post(
            "/admin/providers",
            headers=ADMIN,
            json={"name": "openai-enc", "provider": "openai", "api_key": "real-secret-key"},
        ).json()["id"]
        client.post(
            "/admin/deployments",
            headers=ADMIN,
            json={"model_name": "gpt-4o-mini", "credential_id": cid},
        )
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert seen["auth"] == "Bearer real-secret-key"
