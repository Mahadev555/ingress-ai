from typing import Any
from app.providers.base import ProviderAdapter

class OpenAIAdapter(ProviderAdapter):
    def build_request(self, unified_req: Any, creds: Any) -> dict[str, Any]:
        return unified_req

    def parse_response(self, native_resp: Any) -> Any:
        return native_resp

    async def stream(self, unified_req: Any, creds: Any):
        raise NotImplementedError
