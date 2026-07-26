"""In-memory snapshot of the DB MCP-server registry.

Loaded at startup and refreshed whenever an admin mutates a server, so the hot
path (routing tool calls, listing tools) reads a plain dict instead of hitting
the database. Mirrors app/core/model_registry.py. Upstream auth is decrypted
here, in-process, and never leaves the object.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.secrets import decrypt
from app.db.models import MCPServer


@dataclass
class RegisteredMCPServer:
    name: str
    url: str
    transport: str
    auth_header: Optional[str]
    auth_value: str  # decrypted in-process; the ready-to-send header value
    enabled: bool

    def auth_headers(self) -> dict[str, str]:
        """The header(s) to send upstream, or empty when the server is open."""
        if self.auth_header and self.auth_value:
            return {self.auth_header: self.auth_value}
        return {}


class MCPServerRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, RegisteredMCPServer] = {}

    async def reload(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            rows = (await session.execute(select(MCPServer))).scalars().all()
        self.set([
            RegisteredMCPServer(
                name=r.name,
                url=r.url,
                transport=r.transport,
                auth_header=r.auth_header,
                auth_value=decrypt(r.auth_value) if r.auth_value else "",
                enabled=r.enabled,
            )
            for r in rows
        ])

    def set(self, servers: list[RegisteredMCPServer]) -> None:
        self._servers = {s.name: s for s in servers}

    def is_empty(self) -> bool:
        return not self._servers

    def get(self, name: str) -> Optional[RegisteredMCPServer]:
        return self._servers.get(name)

    def enabled(self) -> list[RegisteredMCPServer]:
        return [s for s in self._servers.values() if s.enabled]

    def enabled_names(self) -> list[str]:
        return [s.name for s in self._servers.values() if s.enabled]


# Process-wide singleton, shared via app.state.mcp_registry too.
registry = MCPServerRegistry()
