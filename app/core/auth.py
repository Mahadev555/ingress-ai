import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VirtualKey

KEY_PREFIX = "sk-ingress-"
PREFIX_VISIBLE_LEN = 18  # "sk-ingress-" + a few chars, safe to display/store


@dataclass
class KeyContext:
    """The policy a virtual key resolves to. Every downstream layer reads this
    one object, which is what keeps multi-tenancy a later config change."""

    key_id: int
    name: str
    tenant_id: str
    allowed_models: list[str] = field(default_factory=list)
    token_budget: Optional[int] = None

    def allows_model(self, model: str) -> bool:
        return not self.allowed_models or model in self.allowed_models


def generate_key() -> tuple[str, str, str]:
    """Return (full_key, visible_prefix, hash). The full key is shown once."""
    full_key = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return full_key, full_key[:PREFIX_VISIBLE_LEN], hash_key(full_key)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


async def resolve_key(session: AsyncSession, token: Optional[str]) -> Optional[KeyContext]:
    """Look up an active virtual key by its hash and build its KeyContext."""
    if not token:
        return None

    result = await session.execute(
        select(VirtualKey).where(
            VirtualKey.key_hash == hash_key(token),
            VirtualKey.active.is_(True),
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        return None

    return KeyContext(
        key_id=key.id,
        name=key.name,
        tenant_id=key.tenant_id,
        allowed_models=list(key.allowed_models or []),
        token_budget=key.token_budget,
    )
