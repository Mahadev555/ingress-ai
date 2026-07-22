"""Token-bucket rate limiting: per key/model, 429 with Retry-After."""

import httpx
import pytest

from app.core.ratelimit import InMemoryTokenBucket, bucket_params

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


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=COMPLETION)


async def test_token_bucket_allows_burst_then_blocks():
    bucket = InMemoryTokenBucket()
    # capacity 2, slow refill so the third call in the burst is denied.
    rate, capacity = 0.001, 2.0

    first = await bucket.acquire("b", rate, capacity)
    second = await bucket.acquire("b", rate, capacity)
    third = await bucket.acquire("b", rate, capacity)

    assert first.allowed and second.allowed
    assert not third.allowed
    assert third.retry_after > 0


async def test_token_bucket_separates_buckets():
    bucket = InMemoryTokenBucket()
    rate, capacity = 0.001, 1.0

    assert (await bucket.acquire("a", rate, capacity)).allowed
    # Different bucket key is unaffected by the first one's consumption.
    assert (await bucket.acquire("b", rate, capacity)).allowed
    assert not (await bucket.acquire("a", rate, capacity)).allowed


def test_bucket_params_from_per_minute():
    rate, capacity = bucket_params(60)
    assert rate == 1.0
    assert capacity == 60.0


def test_endpoint_returns_429_with_retry_after(make_gateway, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")

    with make_gateway(_ok) as client:
        r1 = client.post("/v1/chat/completions", json=CHAT_BODY)
        r2 = client.post("/v1/chat/completions", json=CHAT_BODY)
        r3 = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["error"]["type"] == "rate_limit_exceeded"
    assert int(r3.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_model(make_gateway, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")

    with make_gateway(_ok) as client:
        first_gpt = client.post("/v1/chat/completions", json=CHAT_BODY)
        second_gpt = client.post("/v1/chat/completions", json=CHAT_BODY)
        # A different model has its own bucket, so it is still allowed.
        other_model = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert first_gpt.status_code == 200
    assert second_gpt.status_code == 429
    assert other_model.status_code == 200
