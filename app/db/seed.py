"""One-time seed of the model registry from the AVAILABLE_MODELS env list.

The gateway used to advertise models straight from the env list. Now the DB
model registry is the source of truth, so on first startup (when the registry is
empty) we import the env list into `model_configs` — with each model's provider
inferred from its name. Prices are left unset (there's no hardcoded price table);
add them per model on the Models page if you want cost estimates. After that the
DB is authoritative: edits, additions, and deletions on the Models page stick,
and seeding never runs again (it only fires on an empty table).
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.secrets import encrypt
from app.db.models import ModelConfig, ProviderCredential
from app.providers.registry import provider_for_model

logger = logging.getLogger("ingress.seed")

# Providers whose env key seeds a named credential on first run.
_ENV_PROVIDERS = [
    ("openai", lambda s: s.openai_api_key),
    ("anthropic", lambda s: s.anthropic_api_key),
    ("gemini", lambda s: s.gemini_api_key),
    ("azure", lambda s: s.azure_api_key),
]


async def seed_credentials_if_empty(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> list[str]:
    """Import each configured env provider key as a named, encrypted credential
    (e.g. 'openai-env'), but only if no credentials exist yet. This makes env
    keys manageable in the UI and gives deployments something to reference."""
    async with session_factory() as session:
        count = (await session.execute(select(func.count(ProviderCredential.id)))).scalar_one()
        if count:
            return []

        seeded: list[str] = []
        for provider, get_key in _ENV_PROVIDERS:
            key = get_key(settings)
            if not key:
                continue
            session.add(
                ProviderCredential(
                    name=f"{provider}-env",
                    provider=provider,
                    api_key=encrypt(key),
                )
            )
            seeded.append(provider)
        await session.commit()

    if seeded:
        logger.info("seeded %d provider credential(s) from env keys", len(seeded))
    return seeded


async def seed_models_if_empty(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> list[str]:
    """Populate the model registry from the env list, but only if it's empty.
    Returns the names seeded (empty if the registry already had entries)."""
    async with session_factory() as session:
        count = (await session.execute(select(func.count(ModelConfig.id)))).scalar_one()
        if count:
            return []  # already populated (or user-managed) — leave it alone

        seeded: list[str] = []
        for name in settings.model_list():
            session.add(
                ModelConfig(
                    name=name,
                    provider=provider_for_model(name),
                    enabled=True,
                )
            )
            seeded.append(name)
        await session.commit()

    if seeded:
        logger.info("seeded %d models into the registry from AVAILABLE_MODELS", len(seeded))
    return seeded
