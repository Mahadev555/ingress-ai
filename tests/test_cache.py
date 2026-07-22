"""Exact-match cache: identical request served from cache, logged as a hit."""

import httpx

from app.core.cache import InMemoryCache, cache_key
from app.schemas.unified import ChatCompletionRequest

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "cached answer"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
}

CHAT_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


def _req(**overrides) -> ChatCompletionRequest:
    base = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    base.update(overrides)
    return ChatCompletionRequest.model_validate(base)


# --- unit --------------------------------------------------------------------


def test_cache_key_is_stable_and_ignores_gateway_fields():
    a = cache_key(_req(), "default")
    # Message key order / stream / fallbacks must not change the key.
    b = cache_key(_req(stream=False, fallbacks=["claude-3-5-sonnet"]), "default")
    assert a == b


def test_cache_key_varies_by_content_and_tenant():
    assert cache_key(_req(), "default") != cache_key(_req(temperature=0.5), "default")
    assert cache_key(_req(), "tenant-a") != cache_key(_req(), "tenant-b")


async def test_in_memory_cache_expires():
    cache = InMemoryCache()
    await cache.set("k", {"v": 1}, ttl_seconds=0)
    assert await cache.get("k") is None


# --- end-to-end --------------------------------------------------------------


def test_identical_request_is_served_from_cache(make_gateway, caplog):
    upstream_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        upstream_calls["n"] += 1
        return httpx.Response(200, json=COMPLETION)

    with make_gateway(handler) as client:
        first = client.post("/v1/chat/completions", json=CHAT_BODY)
        with caplog.at_level("INFO", logger="ingress.chat"):
            second = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()
    # The upstream provider was called only once.
    assert upstream_calls["n"] == 1
    assert any("cache hit" in r.message for r in caplog.records)


def test_cache_is_isolated_per_tenant(make_gateway):
    from tests.conftest import ADMIN_TOKEN

    upstream_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        upstream_calls["n"] += 1
        return httpx.Response(200, json=COMPLETION)

    with make_gateway(handler) as client:
        # A second key on a different tenant.
        other = client.post(
            "/admin/keys",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"name": "other", "tenant_id": "tenant-b"},
        ).json()["key"]

        first = client.post("/v1/chat/completions", json=CHAT_BODY)  # default tenant
        client.headers["Authorization"] = f"Bearer {other}"
        second = client.post("/v1/chat/completions", json=CHAT_BODY)  # tenant-b

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "MISS"  # different tenant, no shared hit
    assert upstream_calls["n"] == 2
