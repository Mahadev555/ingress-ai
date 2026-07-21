from dataclasses import dataclass

@dataclass
class KeyContext:
    key_id: str
    provider: str
    provider_api_key: str
    allowed_models: list[str]
    tenant_id: str | None = None

async def resolve_virtual_key(virtual_key: str) -> KeyContext:
    # TODO: look up virtual keys in Postgres and return a normalized KeyContext
    return KeyContext(
        key_id="stub",
        provider="openai",
        provider_api_key="",
        allowed_models=["gpt-4.1"],
        tenant_id=None,
    )
