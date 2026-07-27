"""MCP gateway: one governed MCP endpoint (POST /mcp) fronting upstream servers.

Covers the thin vertical slice — admin registry (auth redacted), the upstream
MCPClient (JSON + SSE transports), and the full client -> gateway -> upstream
round trip with namespacing, scoping, and usage recording.
"""

import json

import httpx
import pytest

from app.core.config import get_settings
from app.mcp.client import MCPClient

ADMIN = {"X-Admin-Token": "test-admin-token"}
UPSTREAM_URL = "http://mock-mcp/mcp"


def _rpc(client, method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload)


def mcp_upstream(request: httpx.Request) -> httpx.Response:
    """A minimal mock MCP server speaking JSON-RPC over plain JSON."""
    body = json.loads(request.content)
    method = body.get("method")
    rid = body.get("id")
    if rid is None:  # notification (e.g. notifications/initialized)
        return httpx.Response(202)
    if method == "initialize":
        return httpx.Response(
            200,
            headers={"Mcp-Session-Id": "sess-1"},
            json={"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "serverInfo": {"name": "mock", "version": "1"},
            }},
        )
    if method == "tools/list":
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [{"name": "echo", "description": "echo back", "inputSchema": {"type": "object"}}]
        }})
    if method == "tools/call":
        args = body["params"]["arguments"]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": f"echoed: {args}"}], "isError": False,
        }})
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                                     "error": {"code": -32601, "message": "no such method"}})


def _enable_mcp(monkeypatch):
    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()


def _register_server(client, name="mock", url=UPSTREAM_URL, auth_value=""):
    return client.post("/admin/mcp/servers", headers=ADMIN, json={
        "name": name, "url": url, "auth_value": auth_value,
    })


# --- config + toggle ---------------------------------------------------------


def test_config_reports_mcp_flag(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway() as client:
        assert client.get("/v1/config").json()["mcp_enabled"] is True


def test_mcp_disabled_by_default(make_gateway):
    """With MCP_ENABLED unset, the endpoint returns a JSON-RPC error, not tools."""
    with make_gateway() as client:
        body = _rpc(client, "initialize").json()
    assert body["error"]["message"].startswith("MCP gateway is disabled")


# --- admin registry ----------------------------------------------------------


def test_admin_server_crud_redacts_auth(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway() as client:
        created = _register_server(client, auth_value="Bearer super-secret")
        assert created.status_code == 200, created.text
        info = created.json()
        # The secret is never echoed back — only a boolean flag.
        assert info["has_auth"] is True
        assert "auth_value" not in info
        assert "super-secret" not in created.text

        listed = client.get("/admin/mcp/servers", headers=ADMIN).json()
        assert [s["name"] for s in listed] == ["mock"]

        sid = info["id"]
        assert client.delete(f"/admin/mcp/servers/{sid}", headers=ADMIN).status_code == 204
        assert client.get("/admin/mcp/servers", headers=ADMIN).json() == []


def test_server_name_rejects_namespace_separator(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway() as client:
        resp = _register_server(client, name="bad__name")
    assert resp.status_code == 400


# --- upstream client (unit) --------------------------------------------------


async def test_client_initialize_list_call():
    transport = httpx.MockTransport(mcp_upstream)
    async with httpx.AsyncClient(transport=transport) as http:
        client = MCPClient(name="mock", url=UPSTREAM_URL, http_client=http)
        tools = await client.list_tools()
        assert [t["name"] for t in tools] == ["echo"]
        result = await client.call_tool("echo", {"x": 1})
        assert result["content"][0]["text"].startswith("echoed")
        # The session id from initialize is captured and reused.
        assert client._session_id == "sess-1"


async def test_client_parses_sse_response():
    """An upstream that replies with text/event-stream is handled too."""
    def sse_upstream(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        rid = body.get("id")
        if rid is None:
            return httpx.Response(202)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid, "result": {}})
        frame = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': rid, 'result': {'tools': [{'name': 'sse_tool'}]}})}\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=frame)

    transport = httpx.MockTransport(sse_upstream)
    async with httpx.AsyncClient(transport=transport) as http:
        client = MCPClient(name="mock", url=UPSTREAM_URL, http_client=http)
        tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["sse_tool"]


# --- full gateway round trip -------------------------------------------------


def test_tools_list_namespaced(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway(mcp_upstream) as client:
        _register_server(client)
        body = _rpc(client, "tools/list").json()
    names = [t["name"] for t in body["result"]["tools"]]
    assert names == ["mock__echo"]  # namespaced {server}__{tool}


def test_tools_call_roundtrip_records_usage(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway(mcp_upstream) as client:
        _register_server(client)
        body = _rpc(client, "tools/call",
                    {"name": "mock__echo", "arguments": {"hi": "there"}}).json()
        assert body["result"]["isError"] is False
        assert "there" in body["result"]["content"][0]["text"]

        # A tool-usage record is written (kind="tool"; server->provider, tool->model).
        recent = client.get("/admin/usage/recent", headers=ADMIN).json()
    assert recent[0]["provider"] == "mock"
    assert recent[0]["model"] == "mock__echo"


def test_tools_call_unknown_namespace(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway(mcp_upstream) as client:
        _register_server(client)
        body = _rpc(client, "tools/call", {"name": "nope", "arguments": {}}).json()
    assert body["error"]["code"] == -32602  # must be "{server}__{tool}"


def test_scoping_denies_disallowed_server(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway(mcp_upstream) as client:
        _register_server(client)
        # A key scoped to a *different* server may not call mock__echo.
        scoped = client.post("/admin/keys", headers=ADMIN, json={
            "name": "scoped", "allowed_servers": ["other"],
        }).json()["key"]
        resp = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {scoped}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "mock__echo", "arguments": {}}},
        ).json()
    assert "may not call" in resp["error"]["message"]


def test_scoped_key_sees_only_allowed_tools(make_gateway, monkeypatch):
    _enable_mcp(monkeypatch)
    with make_gateway(mcp_upstream) as client:
        _register_server(client)
        scoped = client.post("/admin/keys", headers=ADMIN, json={
            "name": "scoped", "allowed_tools": ["mock__something_else"],
        }).json()["key"]
        body = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {scoped}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        ).json()
    assert body["result"]["tools"] == []  # echo is filtered out
