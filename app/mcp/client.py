"""Minimal async MCP client over Streamable HTTP (JSON-RPC 2.0).

One instance fronts one upstream MCP server for the duration of a gateway
request. It performs the `initialize` handshake once, then `tools/list` /
`tools/call`. Responses may come back as `application/json` or as an SSE
(`text/event-stream`) frame; both are handled.

v1 scope: remote HTTP upstreams only (no stdio), and a fresh client (fresh
session) per gateway request. Long-lived session pooling is a later optimization.
"""

import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("ingress.mcp")

# MCP protocol version the gateway advertises to upstreams.
PROTOCOL_VERSION = "2025-06-18"


class MCPError(Exception):
    """An upstream MCP failure (transport, HTTP, or JSON-RPC error)."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code


class MCPClient:
    def __init__(
        self,
        *,
        name: str,
        url: str,
        http_client: httpx.AsyncClient,
        auth_headers: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.url = url
        self._http = http_client
        self._auth = auth_headers or {}
        self._timeout = timeout
        self._session_id: Optional[str] = None
        self._next_id = 0
        self._initialized = False
        self._server_info: dict[str, Any] = {}

    # --- transport -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        headers.update(self._auth)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _post(self, payload: dict) -> httpx.Response:
        try:
            resp = await self._http.post(
                self.url, json=payload, headers=self._headers(), timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise MCPError(f"could not reach MCP server '{self.name}': {exc}") from exc
        # The session id is assigned on the initialize response; reuse it after.
        session_id = resp.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        return resp

    async def _request(self, method: str, params: Optional[dict] = None) -> Any:
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params

        resp = await self._post(payload)
        if resp.status_code >= 400:
            raise MCPError(
                f"MCP server '{self.name}' returned HTTP {resp.status_code} for {method}"
            )

        message = _extract_jsonrpc(resp)
        if message is None:
            raise MCPError(f"MCP server '{self.name}' returned no JSON-RPC response for {method}")
        if message.get("error"):
            err = message["error"]
            raise MCPError(err.get("message", "upstream MCP error"), err.get("code"))
        return message.get("result")

    async def _notify(self, method: str, params: Optional[dict] = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        await self._post(payload)  # notifications get no response body

    # --- MCP surface ---------------------------------------------------------

    async def initialize(self) -> dict:
        """Handshake once per client; subsequent calls are no-ops."""
        if self._initialized:
            return self._server_info
        result = await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ingress-ai", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized")
        self._initialized = True
        self._server_info = result or {}
        return self._server_info

    async def list_tools(self) -> list[dict]:
        await self.initialize()
        result = await self._request("tools/list")
        return list((result or {}).get("tools", []))

    async def call_tool(self, name: str, arguments: Optional[dict]) -> dict:
        await self.initialize()
        result = await self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return result or {}


def _extract_jsonrpc(resp: httpx.Response) -> Optional[dict]:
    """Pull the JSON-RPC message out of either a plain JSON body or an SSE frame."""
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return _parse_sse(resp.text)
    body = resp.text.strip()
    if not body:
        return None
    data = json.loads(body)
    if isinstance(data, list):  # batch — return the first response-bearing message
        for item in data:
            if isinstance(item, dict) and ("result" in item or "error" in item):
                return item
        return data[0] if data else None
    return data


def _parse_sse(text: str) -> Optional[dict]:
    """Return the first `data:` payload that is a JSON-RPC response/error."""
    data_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
            continue
        if line == "" and data_lines:
            message = _try_json("\n".join(data_lines))
            data_lines = []
            if isinstance(message, dict) and ("result" in message or "error" in message):
                return message
    if data_lines:
        message = _try_json("\n".join(data_lines))
        if isinstance(message, dict):
            return message
    return None


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
