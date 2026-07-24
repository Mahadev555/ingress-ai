"""Spend tags + budget alert webhooks (feature ③)."""

import httpx

from app.core.auth import KeyContext
from app.observability import alerts

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


def _handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=CHAT_OK)


# --- tags --------------------------------------------------------------------


def test_usage_by_tag_merges_key_and_header_tags(make_gateway):
    with make_gateway(_handler) as client:
        created = client.post(
            "/admin/keys", headers=ADMIN, json={"name": "k", "tags": ["team-a"]}
        )
        key = created.json()["key"]

        r = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "X-Tags": "feature-x, feature-x"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200

        by_tag = {t["tag"]: t for t in client.get("/admin/usage/by-tag", headers=ADMIN).json()}
        assert set(by_tag) == {"team-a", "feature-x"}  # key tag + request tag, de-duped
        assert by_tag["team-a"]["requests"] == 1
        assert by_tag["feature-x"]["total_tokens"] == 3


# --- budget alerts -----------------------------------------------------------


class _StubClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def post(self, url, json=None, timeout=None):
        self.posts.append(json)


async def test_soft_budget_alert_fires_once():
    alerts.reset()
    client = _StubClient()
    key = KeyContext(key_id=1, name="k", tenant_id="default", token_budget=10, tokens_used=9)

    await alerts.check_key_budget(client, "http://hook", 0.8, key)
    assert len(client.posts) == 1
    assert "budget" in client.posts[0]["text"]

    # Same window + level → de-duplicated, no repeat spam.
    await alerts.check_key_budget(client, "http://hook", 0.8, key)
    assert len(client.posts) == 1


async def test_no_alert_below_threshold():
    alerts.reset()
    client = _StubClient()
    key = KeyContext(key_id=2, name="k", tenant_id="default", token_budget=10, tokens_used=1)
    await alerts.check_key_budget(client, "http://hook", 0.8, key)
    assert client.posts == []


async def test_hard_cost_alert_fires():
    alerts.reset()
    client = _StubClient()
    key = KeyContext(key_id=3, name="k", tenant_id="default", cost_budget_usd=1.0, cost_used=1.5)
    await alerts.check_key_budget(client, "http://hook", 0.8, key)
    assert len(client.posts) == 1
    assert "🚨" in client.posts[0]["text"]


async def test_disabled_when_no_webhook():
    alerts.reset()
    client = _StubClient()
    key = KeyContext(key_id=4, name="k", tenant_id="default", token_budget=10, tokens_used=10)
    await alerts.check_key_budget(client, "", 0.8, key)  # empty URL disables alerting
    assert client.posts == []
