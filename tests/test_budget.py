"""Token budget enforcement: a key over its cap is blocked with 429."""

import httpx

CHAT_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}

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


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=COMPLETION)


def test_request_under_budget_is_allowed(make_gateway):
    with make_gateway(_ok, token_budget=100) as client:
        resp = client.post("/v1/chat/completions", json=CHAT_BODY)
    assert resp.status_code == 200


def test_budget_blocks_once_exceeded(make_gateway):
    # Budget of 5 tokens; the first call (8 tokens) lands, the next is blocked.
    with make_gateway(_ok, token_budget=5) as client:
        first = client.post("/v1/chat/completions", json=CHAT_BODY)
        second = client.post("/v1/chat/completions", json=CHAT_BODY)

    assert first.status_code == 200  # used 0 of 5 at request time
    assert second.status_code == 429  # already used 8 >= 5
    assert second.json()["error"]["type"] == "budget_exceeded"


def test_no_budget_means_unlimited(make_gateway):
    with make_gateway(_ok) as client:  # token_budget=None
        for _ in range(3):
            resp = client.post("/v1/chat/completions", json=CHAT_BODY)
            assert resp.status_code == 200
