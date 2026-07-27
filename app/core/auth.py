import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Team, UsageRecord, VirtualKey

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
    # MCP scoping: empty = all enabled servers / all their tools. allowed_tools
    # holds namespaced "{server}__{tool}".
    allowed_servers: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    token_budget: Optional[int] = None
    cost_budget_usd: Optional[float] = None
    budget_period: str = "total"
    tokens_used: int = 0  # tokens within the budget window (only computed when budgeted)
    cost_used: float = 0.0  # cost within the budget window
    rate_limit_per_minute: Optional[int] = None  # None → use the global default
    tpm_limit: Optional[int] = None
    max_concurrency: Optional[int] = None
    expires_at: Optional[datetime] = None
    # Team (tenancy) context — populated only when the key belongs to a team.
    team_id: Optional[int] = None
    team_allowed_models: list[str] = field(default_factory=list)
    team_token_budget: Optional[int] = None
    team_cost_budget_usd: Optional[float] = None
    team_budget_period: str = "total"
    team_tokens_used: int = 0
    team_cost_used: float = 0.0

    def allows_model(self, model: str) -> bool:
        if self.allowed_models and model not in self.allowed_models:
            return False
        if self.team_allowed_models and model not in self.team_allowed_models:
            return False
        return True

    def may_use(self, server: str, tool: Optional[str] = None) -> bool:
        """Whether this key may reach an MCP server (and optionally a specific
        namespaced tool). Empty scope lists mean "no restriction"."""
        if self.allowed_servers and server not in self.allowed_servers:
            return False
        if tool is not None and self.allowed_tools and tool not in self.allowed_tools:
            return False
        return True

    def budget_exceeded(self) -> bool:
        if self.token_budget is not None and self.tokens_used >= self.token_budget:
            return True
        if self.cost_budget_usd is not None and self.cost_used >= self.cost_budget_usd:
            return True
        return self.team_budget_exceeded()

    def team_budget_exceeded(self) -> bool:
        if self.team_id is None:
            return False
        if self.team_token_budget is not None and self.team_tokens_used >= self.team_token_budget:
            return True
        if (
            self.team_cost_budget_usd is not None
            and self.team_cost_used >= self.team_cost_budget_usd
        ):
            return True
        return False

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:  # SQLite may return naive datetimes
            expires = expires.replace(tzinfo=timezone.utc)
        return now >= expires


def generate_key() -> tuple[str, str, str]:
    """Return (full_key, visible_prefix, hash). The full key is shown once."""
    full_key = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return full_key, full_key[:PREFIX_VISIBLE_LEN], hash_key(full_key)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def _budget_window_start(period: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Start of the current budget window, or None for a lifetime ('total') budget."""
    now = now or datetime.now(timezone.utc)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


async def usage_since(
    session: AsyncSession, key_id: int, since: Optional[datetime]
) -> tuple[int, float]:
    """Return (total_tokens, total_cost_usd) for a key, optionally since a time."""
    query = select(
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
    ).where(UsageRecord.key_id == key_id)
    if since is not None:
        query = query.where(UsageRecord.created_at >= since)
    tokens, cost = (await session.execute(query)).one()
    return int(tokens), float(cost)


async def tokens_in_last_minute(session: AsyncSession, key_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(seconds=60)
    tokens, _ = await usage_since(session, key_id, since)
    return tokens


async def team_usage_since(
    session: AsyncSession, team_id: int, since: Optional[datetime]
) -> tuple[int, float]:
    """(tokens, cost) across every key belonging to a team, optionally windowed."""
    member_ids = select(VirtualKey.id).where(VirtualKey.team_id == team_id)
    query = select(
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
    ).where(UsageRecord.key_id.in_(member_ids))
    if since is not None:
        query = query.where(UsageRecord.created_at >= since)
    tokens, cost = (await session.execute(query)).one()
    return int(tokens), float(cost)


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

    tokens_used = 0
    cost_used = 0.0
    if key.token_budget is not None or key.cost_budget_usd is not None:
        since = _budget_window_start(key.budget_period)
        tokens_used, cost_used = await usage_since(session, key.id, since)

    # Resolve the team (tenancy) context, computing its windowed spend only when
    # the team actually carries a budget — one extra query, and only if needed.
    team = await session.get(Team, key.team_id) if key.team_id else None
    team_tokens_used = 0
    team_cost_used = 0.0
    if team is not None and (team.token_budget is not None or team.cost_budget_usd is not None):
        since = _budget_window_start(team.budget_period or "total")
        team_tokens_used, team_cost_used = await team_usage_since(session, team.id, since)

    return KeyContext(
        key_id=key.id,
        name=key.name,
        tenant_id=key.tenant_id,
        allowed_models=list(key.allowed_models or []),
        allowed_servers=list(key.allowed_servers or []),
        allowed_tools=list(key.allowed_tools or []),
        tags=list(key.tags or []),
        token_budget=key.token_budget,
        cost_budget_usd=key.cost_budget_usd,
        budget_period=key.budget_period or "total",
        tokens_used=tokens_used,
        cost_used=cost_used,
        rate_limit_per_minute=key.rate_limit_per_minute,
        tpm_limit=key.tpm_limit,
        max_concurrency=key.max_concurrency,
        expires_at=key.expires_at,
        team_id=key.team_id,
        team_allowed_models=list(team.allowed_models or []) if team else [],
        team_token_budget=team.token_budget if team else None,
        team_cost_budget_usd=team.cost_budget_usd if team else None,
        team_budget_period=(team.budget_period or "total") if team else "total",
        team_tokens_used=team_tokens_used,
        team_cost_used=team_cost_used,
    )
