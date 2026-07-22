from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from app.schemas.unified import ChatCompletionRequest, ChatCompletionResponse


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
