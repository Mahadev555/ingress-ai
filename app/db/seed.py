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
from app.db.models import ModelConfig
from app.providers.registry import provider_for_model

logger = logging.getLogger("ingress.seed")


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
