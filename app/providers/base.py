from abc import ABC, abstractmethod
from typing import Any

class ProviderAdapter(ABC):
    @abstractmethod
    def build_request(self, unified_req: Any, creds: Any) -> Any:
        pass

    @abstractmethod
    def parse_response(self, native_resp: Any) -> Any:
        pass

    @abstractmethod
    async def stream(self, unified_req: Any, creds: Any):
        raise NotImplementedError
