from typing import Any

async def select_provider(model: str, key_context: Any) -> dict[str, Any]:
    # TODO: select a provider and model based on health, cost, and policy
    return {"provider": key_context.provider, "model": model}
