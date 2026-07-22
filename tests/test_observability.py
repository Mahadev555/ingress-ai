"""Observability: usage records, redacting log filter, Prometheus metrics."""

import logging

import httpx

from app.observability.logging import RedactingFilter, redact
from app.observability.pricing import cost_usd
from tests.conftest import ADMIN_TOKEN

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}

CHAT_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=COMPLETION)


# --- redaction ---------------------------------------------------------------


def test_redact_scrubs_bearer_and_api_keys():
    assert redact("Authorization: Bearer sk-secret-abc") == "Authorization: Bearer ***"
    assert redact("virtual key sk-ingress-abc123 used") == "virtual key sk-*** used"


def test_redacting_filter_rewrites_record():
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "call with sk-abc123 done", None, None
    )
    RedactingFilter().filter(record)
    message = record.getMessage()
    assert "sk-abc123" not in message
    assert "sk-***" in message


# --- pricing -----------------------------------------------------------------


def test_cost_uses_longest_prefix_match():
    # 1M input tokens at gpt-4o-mini's input price.
    assert cost_usd("gpt-4o-mini", 1_000_000, 0) == 0.15
    # Versioned name still resolves via prefix.
    assert cost_usd("gpt-4o-mini-2024-07-18", 1_000_000, 0) == 0.15


def test_cost_is_zero_for_unknown_model():
    assert cost_usd("mystery-model", 1000, 1000) == 0.0


# --- end-to-end --------------------------------------------------------------


def test_usage_is_recorded(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        summary = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 8
    assert summary["total_cost_usd"] > 0


def test_metrics_endpoint_exposes_counters(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        metrics = client.get("/metrics")

    assert metrics.status_code == 200
    body = metrics.text
    assert "ingress_requests_total" in body
    assert "ingress_tokens_total" in body
