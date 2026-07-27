"""The gateway's MCP endpoint: one governed MCP server (POST /mcp) fronting many
upstream MCP servers.

Speaks JSON-RPC 2.0 over Streamable HTTP. Authenticated by an existing virtual
key (Bearer sk-ingress-…). Tools from every allowed upstream are namespaced
`{server}__{tool}` and merged; a `tools/call` is demuxed back to its server,
scope-checked against the key, forwarded, and written to the usage ledger.

v1 surface: initialize, tools/list, tools/call (resources/* and prompts/* are a
later phase). See plan/MCP-Gateway-Build-Plan.md.
"""

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.deps import require_key
from app.core.auth import KeyContext
from app.core.config import Settings, get_settings
from app.mcp.client import MCPClient, MCPError
from app.mcp.registry import RegisteredMCPServer
from app.observability.usage import record_usage
from app.schemas.usage import UsageEvent

logger = logging.getLogger("ingress.mcp")

router = APIRouter()

# Tool names are namespaced "{server}__{tool}" so tools from different upstreams
# never collide and a call can be demuxed back to its server.
NAMESPACE_SEP = "__"

# JSON-RPC error codes (a subset of the spec plus one app-level code).
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_SERVER_ERROR = -32000

SERVER_INFO = {"name": "ingress-ai", "version": "0.1.0"}


def _result(request_id: Any, result: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


def _make_client(
    server: RegisteredMCPServer, http: httpx.AsyncClient, settings: Settings
) -> MCPClient:
    return MCPClient(
        name=server.name,
        url=server.url,
        http_client=http,
        auth_headers=server.auth_headers(),
        timeout=settings.mcp_tool_timeout,
    )


def _visible_servers(request: Request, key: KeyContext) -> list[RegisteredMCPServer]:
    """Enabled upstream servers this key is allowed to see."""
    registry = request.app.state.mcp_registry
    return [s for s in registry.enabled() if key.may_use(s.name)]


@router.post("")
async def mcp_endpoint(
    request: Request,
    background: BackgroundTasks,
    key: KeyContext = Depends(require_key),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Single JSON-RPC entrypoint. Dispatches by method; returns a JSON-RPC
    response (notifications get 202 with no body)."""
    if not settings.mcp_enabled:
        return _error(None, _SERVER_ERROR, "MCP gateway is disabled (set MCP_ENABLED=true)")

    try:
        message = await request.json()
    except Exception:
        return _error(None, _INVALID_PARAMS, "request body is not valid JSON")

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, _INVALID_PARAMS, "expected a JSON-RPC 2.0 request")

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no id) are fire-and-forget — ack with 202, no body.
    if request_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return Response(status_code=202)

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "tools/list":
        return await _tools_list(request, key, settings, request_id)

    if method == "tools/call":
        return await _tools_call(request, background, key, settings, request_id, params)

    return _error(request_id, _METHOD_NOT_FOUND, f"method '{method}' is not supported")


async def _tools_list(
    request: Request, key: KeyContext, settings: Settings, request_id: Any
) -> JSONResponse:
    """Fan out tools/list to every allowed upstream, namespace, and merge."""
    servers = _visible_servers(request, key)
    http: httpx.AsyncClient = request.app.state.http_client

    async def fetch(server: RegisteredMCPServer) -> list[dict]:
        try:
            tools = await _make_client(server, http, settings).list_tools()
        except MCPError as exc:
            logger.warning("tools/list failed for MCP server '%s': %s", server.name, exc)
            return []
        namespaced = []
        for tool in tools:
            name = tool.get("name")
            if not name or not key.may_use(server.name, f"{server.name}{NAMESPACE_SEP}{name}"):
                continue
            entry = dict(tool)
            entry["name"] = f"{server.name}{NAMESPACE_SEP}{name}"
            namespaced.append(entry)
        return namespaced

    results = await asyncio.gather(*(fetch(s) for s in servers))
    merged = [tool for group in results for tool in group]
    return _result(request_id, {"tools": merged})


async def _tools_call(
    request: Request,
    background: BackgroundTasks,
    key: KeyContext,
    settings: Settings,
    request_id: Any,
    params: dict,
) -> JSONResponse:
    """Resolve a namespaced tool to its server, scope-check, forward, and record."""
    namespaced = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(namespaced, str) or NAMESPACE_SEP not in namespaced:
        return _error(request_id, _INVALID_PARAMS, "tool name must be '{server}__{tool}'")

    server_name, _, tool_name = namespaced.partition(NAMESPACE_SEP)
    server = request.app.state.mcp_registry.get(server_name)
    if server is None or not server.enabled:
        return _error(request_id, _INVALID_PARAMS, f"unknown MCP server '{server_name}'")
    if not key.may_use(server_name, namespaced):
        return _error(request_id, _SERVER_ERROR, f"this key may not call '{namespaced}'")

    http: httpx.AsyncClient = request.app.state.http_client
    started = time.perf_counter()
    status = 200
    try:
        result = await _make_client(server, http, settings).call_tool(tool_name, arguments)
    except MCPError as exc:
        status = 502
        result = {
            "content": [{"type": "text", "text": f"MCP tool error: {exc}"}],
            "isError": True,
        }
    latency_ms = int((time.perf_counter() - started) * 1000)

    # One usage record per tool call, off the hot path. Server -> provider,
    # tool -> model, so it shares the existing ledger and dashboards.
    background.add_task(
        record_usage,
        request.app.state.session_factory,
        UsageEvent(
            key_id=key.key_id,
            tenant_id=key.tenant_id,
            kind="tool",
            provider=server_name,
            model=namespaced,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            latency_ms=latency_ms,
            status=status,
            cache_hit=False,
            trace_id=getattr(request.state, "request_id", None),
            tags=key.tags or [],
        ),
    )
    return _result(request_id, result)
