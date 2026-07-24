"""Observability: usage records, redacting log filter, Prometheus metrics."""

import logging

import httpx

from app.core.config import get_settings
from app.observability import pricing
from app.observability.logging import RedactingFilter, redact
from app.observability.pricing import cost_usd
from tests.conftest import ADMIN_TOKEN

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def _price_model(client, name="gpt-4o-mini", inp=0.15, out=0.60):
    """Set a registry price for a model (there are no hardcoded prices)."""
    models = client.get("/admin/models", headers=ADMIN).json()
    m = next(x for x in models if x["name"] == name)
    client.patch(
        f"/admin/models/{m['id']}",
        headers=ADMIN,
        json={"input_price_per_1m": inp, "output_price_per_1m": out},
    )

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


def test_cost_uses_registry_price():
    # Pricing comes only from the registry (exact model name), not a static table.
    pricing.set_overrides({"gpt-4o-mini": (0.15, 0.60)})
    try:
        assert cost_usd("gpt-4o-mini", 1_000_000, 0) == 0.15
    finally:
        pricing.set_overrides({})


def test_cost_is_zero_for_unpriced_model():
    pricing.set_overrides({})
    assert cost_usd("mystery-model", 1000, 1000) == 0.0


# --- end-to-end --------------------------------------------------------------


def test_usage_is_recorded(make_gateway):
    with make_gateway(_ok) as client:
        _price_model(client)  # cost only accrues when the model has a registry price
        client.post("/v1/chat/completions", json=CHAT_BODY)
        summary = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 8
    assert summary["total_cost_usd"] > 0


def test_cost_tracking_can_be_disabled(make_gateway, monkeypatch):
    monkeypatch.setenv("COST_TRACKING_ENABLED", "false")
    get_settings.cache_clear()
    with make_gateway(_ok) as client:
        _price_model(client)  # priced, but cost tracking is off → still $0
        client.post("/v1/chat/completions", json=CHAT_BODY)
        summary = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 8
    assert summary["total_cost_usd"] == 0
    assert client.get("/v1/config").json()["cost_tracking_enabled"] is False


def test_usage_summary_splits_input_output(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        summary = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert summary["prompt_tokens"] == 5  # input
    assert summary["completion_tokens"] == 3  # output
    assert summary["total_tokens"] == 8


def test_usage_by_key_attributes_tokens(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        by_key = client.get("/admin/usage/by-key", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert len(by_key) == 1
    row = by_key[0]
    assert row["name"] == "test"  # the key make_gateway created
    assert row["requests"] == 1
    assert row["prompt_tokens"] == 5
    assert row["completion_tokens"] == 3
    assert row["total_tokens"] == 8


def test_usage_by_model_breakdown(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        by_model = client.get("/admin/usage/by-model", headers={"X-Admin-Token": ADMIN_TOKEN}).json()

    assert len(by_model) == 1
    row = by_model[0]
    assert row["model"] == "gpt-4o-mini"
    assert row["provider"] == "openai"
    assert row["prompt_tokens"] == 5
    assert row["completion_tokens"] == 3
    assert row["total_tokens"] == 8


def test_metrics_endpoint_exposes_counters(make_gateway):
    with make_gateway(_ok) as client:
        client.post("/v1/chat/completions", json=CHAT_BODY)
        metrics = client.get("/metrics")

    assert metrics.status_code == 200
    body = metrics.text
    assert "ingress_requests_total" in body
    assert "ingress_tokens_total" in body
