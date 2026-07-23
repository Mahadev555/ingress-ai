"""/v1/embeddings: OpenAI passthrough and unsupported-provider handling."""

import httpx

EMB_OK = {
    "object": "list",
    "model": "text-embedding-3-small",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
    "usage": {"prompt_tokens": 3, "total_tokens": 3},
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json=EMB_OK)
    return httpx.Response(404, json={"error": {"message": "not found"}})


def test_openai_embeddings_passthrough(make_gateway):
    with make_gateway(_handler) as client:
        r = client.post(
            "/v1/embeddings",
            json={"model": "text-embedding-3-small", "input": "hello world"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["embedding"] == [0.1, 0.2, 0.3]


def test_anthropic_embeddings_unsupported(make_gateway):
    with make_gateway(_handler) as client:
        r = client.post(
            "/v1/embeddings",
            json={"model": "claude-3-5-sonnet", "input": "hello"},
        )
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "embeddings_unsupported"
