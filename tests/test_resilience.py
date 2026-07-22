"""Retry + fallback + circuit breaker: kill a provider, fail over via the router."""

import httpx
import pytest

from app.resilience.retry import ClientError, RetryConfig, TransientError, with_retries
from app.router.health import CircuitBreaker

# --- unit: retry -------------------------------------------------------------

NO_DELAY = RetryConfig(attempts=3, base_delay=0.0, max_delay=0.0)


async def test_with_retries_recovers_after_transient_failures():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError(503, "flaky")
        return "ok"

    result = await with_retries(factory, NO_DELAY)
    assert result == "ok"
    assert calls["n"] == 3


async def test_with_retries_gives_up_and_reraises():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise TransientError(500, "always down")

    with pytest.raises(TransientError):
        await with_retries(factory, NO_DELAY)
    assert calls["n"] == 3  # exactly `attempts` tries, no more


async def test_client_error_is_not_retried():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise ClientError(400, {"error": "bad"})

    with pytest.raises(ClientError):
        await with_retries(factory, NO_DELAY)
    assert calls["n"] == 1  # non-retryable: tried once


# --- unit: circuit breaker ---------------------------------------------------


def test_circuit_opens_after_threshold_and_half_opens():
    breaker = CircuitBreaker(fail_threshold=2, reset_timeout=0.0)

    assert not breaker.is_open("openai")
    breaker.record_failure("openai")
    assert not breaker.is_open("openai")  # one failure, still closed
    breaker.record_failure("openai")
    # reset_timeout=0 means it immediately half-opens on the next check.
    assert not breaker.is_open("openai")

    breaker.record_success("openai")
    assert not breaker.is_open("openai")


def test_circuit_stays_open_within_timeout():
    breaker = CircuitBreaker(fail_threshold=1, reset_timeout=60.0)
    breaker.record_failure("gemini")
    assert breaker.is_open("gemini")


# --- end-to-end: failover ----------------------------------------------------

GEMINI_PAYLOAD = {
    "candidates": [
        {"content": {"parts": [{"text": "from gemini"}]}, "finishReason": "STOP", "index": 0}
    ],
    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3},
}


def test_failover_to_fallback_provider(make_gateway):
    seen = {"openai": 0, "gemini": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "openai.com" in url:
            seen["openai"] += 1
            return httpx.Response(503, json={"error": {"message": "down"}})
        seen["gemini"] += 1
        return httpx.Response(200, json=GEMINI_PAYLOAD)

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "fallbacks": ["gemini-1.5-flash"],
            },
        )

    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "from gemini"
    # Primary was retried (transient 503) then we failed over to the fallback.
    assert seen["openai"] >= 1
    assert seen["gemini"] == 1


def test_client_error_is_relayed_without_failover(make_gateway):
    seen = {"openai": 0, "gemini": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "openai.com" in str(request.url):
            seen["openai"] += 1
            return httpx.Response(400, json={"error": {"message": "bad request"}})
        seen["gemini"] += 1
        return httpx.Response(200, json=GEMINI_PAYLOAD)

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "fallbacks": ["gemini-1.5-flash"],
            },
        )

    assert resp.status_code == 400
    assert seen["openai"] == 1  # tried once, not retried
    assert seen["gemini"] == 0  # 4xx is not a failover trigger


def test_upstream_error_is_normalized(make_gateway):
    # A verbose provider 429 body must be condensed into a clean, typed envelope
    # (never the raw provider fields), and tagged as an upstream — not gateway — error.
    verbose = {
        "error": {
            "message": "Resource has been exhausted (check quota). " * 20,
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"@type": "RetryInfo", "retryDelay": "30s"}],
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=verbose)

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 429
    err = resp.json()["error"]
    assert err["type"] == "upstream_rate_limit"
    assert err["provider"] == "openai"
    assert len(err["message"]) <= 200  # condensed
    assert "details" not in err and "status" not in err  # no raw provider fields leaked


def test_unconfigured_provider_returns_clean_error(make_gateway, monkeypatch):
    # No key for OpenAI -> a clear 503 instead of a cryptic empty-Bearer failure.
    monkeypatch.setenv("OPENAI_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("upstream should not be called when unconfigured")

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["type"] == "provider_not_configured"
    assert "OPENAI_API_KEY" in body["error"]["message"]


def test_all_providers_down_returns_error(make_gateway):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with make_gateway(handler) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "bad_gateway"
