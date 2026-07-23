"""In-memory snapshot of the DB model registry.

Loaded once at startup and refreshed whenever an admin mutates a model, so the
hot path (routing, pricing, model listing) reads a plain dict instead of hitting
the database on every request. When the registry is empty the gateway falls back
to the AVAILABLE_MODELS env list and the static price table.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ModelConfig
from app.observability import pricing


@dataclass
class RegisteredModel:
    name: str
    provider: str
    alias_of: Optional[str]
    input_price_per_1m: Optional[float]
    output_price_per_1m: Optional[float]
    default_rate_limit_per_minute: Optional[int]
    default_tpm_limit: Optional[int]
    enabled: bool


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, RegisteredModel] = {}

    async def reload(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            rows = (await session.execute(select(ModelConfig))).scalars().all()
        self.set([
            RegisteredModel(
                name=r.name,
                provider=r.provider,
                alias_of=r.alias_of,
                input_price_per_1m=r.input_price_per_1m,
                output_price_per_1m=r.output_price_per_1m,
                default_rate_limit_per_minute=r.default_rate_limit_per_minute,
                default_tpm_limit=r.default_tpm_limit,
                enabled=r.enabled,
            )
            for r in rows
        ])

    def set(self, models: list[RegisteredModel]) -> None:
        self._models = {m.name: m for m in models}
        # Push per-model prices into the pricing module's override table.
        pricing.set_overrides({
            m.name: (m.input_price_per_1m, m.output_price_per_1m)
            for m in models
            if m.input_price_per_1m is not None and m.output_price_per_1m is not None
        })

    def is_empty(self) -> bool:
        return not self._models

    def enabled_names(self) -> list[str]:
        return [m.name for m in self._models.values() if m.enabled]

    def resolve_alias(self, model: str) -> str:
        entry = self._models.get(model)
        return entry.alias_of if entry and entry.alias_of else model

    def is_enabled(self, model: str) -> bool:
        entry = self._models.get(model)
        return entry.enabled if entry else True  # unknown models are allowed

    def defaults(self, model: str) -> tuple[Optional[int], Optional[int]]:
        entry = self._models.get(model)
        if not entry:
            return None, None
        return entry.default_rate_limit_per_minute, entry.default_tpm_limit


# Process-wide singleton, shared via app.state.model_registry too.
registry = ModelRegistry()
