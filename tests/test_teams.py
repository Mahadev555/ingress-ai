"""Team tenancy layer: shared budgets + allowed models (feature ②)."""

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
    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
}


def _handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=CHAT_OK)


def _new_key(client, **body):
    r = client.post("/admin/keys", headers=ADMIN, json=body)
    assert r.status_code == 200, r.text
    return r.json()["key"]


def _chat(client, key, model="gpt-4o-mini"):
    return client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
    )


def test_team_allowed_models_narrows_key(make_gateway):
    with make_gateway(_handler) as client:
        team = client.post(
            "/admin/teams", headers=ADMIN,
            json={"name": "t", "allowed_models": ["gpt-4o-mini"]},
        ).json()
        key = _new_key(client, name="k", team_id=team["id"])  # key itself allows any model

        assert _chat(client, key, "gpt-4o-mini").status_code == 200
        denied = _chat(client, key, "gpt-4o")  # team doesn't allow it
        assert denied.status_code == 403
        # model_not_allowed is raised via HTTPException, so it's under "detail".
        assert denied.json()["detail"]["error"]["type"] == "model_not_allowed"


def test_team_token_budget_is_shared_across_keys(make_gateway):
    with make_gateway(_handler) as client:
        team = client.post(
            "/admin/teams", headers=ADMIN, json={"name": "t", "token_budget": 2}
        ).json()
        k1 = _new_key(client, name="k1", team_id=team["id"])
        k2 = _new_key(client, name="k2", team_id=team["id"])

        # k1 spends 3 tokens, exhausting the team's budget of 2.
        assert _chat(client, k1).status_code == 200
        # k2 shares the same team budget, so it's now blocked.
        blocked = _chat(client, k2)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["type"] == "budget_exceeded"


def test_team_usage_aggregates_member_keys(make_gateway):
    with make_gateway(_handler) as client:
        team = client.post("/admin/teams", headers=ADMIN, json={"name": "t"}).json()
        k1 = _new_key(client, name="k1", team_id=team["id"])
        k2 = _new_key(client, name="k2", team_id=team["id"])
        _chat(client, k1)
        _chat(client, k2)

        usage = client.get(f"/admin/teams/{team['id']}/usage", headers=ADMIN).json()
        assert usage["requests"] == 2
        assert usage["total_tokens"] == 6  # 3 tokens each
