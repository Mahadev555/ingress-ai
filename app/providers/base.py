import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse


class UpstreamStreamError(Exception):
    """The provider returned a non-200 status when opening a stream. Raised
    before any bytes are relayed so the gateway can surface a real HTTP error
    instead of a fake 200 empty stream."""

    def __init__(self, status_code: int, body: Optional[dict]) -> None:
        super().__init__(f"upstream returned {status_code}")
        self.status_code = status_code
        self.body = body


async def read_stream_error(upstream: httpx.Response) -> Optional[dict]:
    """Read and JSON-parse an errored streaming response body, if possible."""
    try:
        raw = await upstream.aread()
        return json.loads(raw)
    except Exception:
        return None


@dataclass
class ProviderCreds:
    """Real upstream credentials and endpoint for a provider call."""

    api_key: str
    base_url: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NativeRequest:
    """A provider-native HTTP request, ready to hand to httpx."""

    method: str
    url: str
    headers: dict[str, str]
    json: dict[str, Any]


class ProviderAdapter(ABC):
    """Contract every provider implements: build, parse, stream.

    The router and API layers only ever speak the unified schema; the adapter
    is the single place that knows a provider's native wire format.
    """

    @abstractmethod
    def build_request(self, req: ChatCompletionRequest, creds: ProviderCreds) -> NativeRequest:
        """Translate a unified request into a provider-native HTTP request."""

    @abstractmethod
    def parse_response(self, payload: dict[str, Any]) -> ChatCompletionResponse:
        """Translate a provider-native success payload into a unified response."""

    @abstractmethod
    def stream(
        self,
        req: ChatCompletionRequest,
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[bytes]:
        """Yield unified SSE chunks (``data: {...}\\n\\n``) for a streaming call."""
