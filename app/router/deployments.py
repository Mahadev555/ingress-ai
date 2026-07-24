"""Multi-deployment routing + load balancing.

A public model name (e.g. ``gpt-4o-mini``) can map to many *deployments* — the
same model reachable through different provider keys, regions, or base URLs.
When deployments exist for a model, the router spreads traffic across the healthy
ones instead of always hitting one upstream. This is the core gateway competency
that turns "one key per provider" into real load balancing + key failover.

Empty registry ⇒ the gateway falls back to the single env-configured credential
per provider (unchanged behavior), so this is fully additive.

Load-balancing state (in-flight counts, recent latency) is per-process — enough
to balance within a replica; a shared (Redis) view is a clean later addition.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ModelDeployment

STRATEGIES = {"simple-shuffle", "least-busy", "latency"}


@dataclass
class Deployment:
    id: int
    model_name: str
    provider: str
    api_key: str
    base_url: Optional[str]
    weight: int
    enabled: bool


@dataclass
class _Stats:
    in_flight: int = 0
    # Exponentially-weighted moving average of latency (ms); None until seen.
    latency_ewma: Optional[float] = None


class DeploymentRegistry:
    def __init__(self) -> None:
        self._by_model: dict[str, list[Deployment]] = {}
        self._stats: dict[int, _Stats] = {}

    async def reload(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        async with session_factory() as session:
            rows = (await session.execute(select(ModelDeployment))).scalars().all()
        self.set(
            [
                Deployment(
                    id=r.id,
                    model_name=r.model_name,
                    provider=r.provider,
                    api_key=r.api_key,
                    base_url=r.base_url,
                    weight=max(1, r.weight or 1),
                    enabled=r.enabled,
                )
                for r in rows
            ]
        )

    def set(self, deployments: list[Deployment]) -> None:
        by_model: dict[str, list[Deployment]] = {}
        for d in deployments:
            by_model.setdefault(d.model_name, []).append(d)
        self._by_model = by_model
        # Drop stats for deployments that no longer exist.
        live = {d.id for d in deployments}
        self._stats = {i: s for i, s in self._stats.items() if i in live}

    def has(self, model_name: str) -> bool:
        return any(d.enabled for d in self._by_model.get(model_name, []))

    def ordered(self, model_name: str, strategy: str) -> list[Deployment]:
        """Enabled deployments for a model, ordered best-first per the strategy.

        The ordering is also a failover chain: if the first pick errors, the
        caller's fallback loop tries the next deployment (a different key)."""
        pool = [d for d in self._by_model.get(model_name, []) if d.enabled]
        if len(pool) <= 1:
            return pool

        if strategy == "least-busy":
            return sorted(pool, key=lambda d: self._stat(d.id).in_flight)
        if strategy == "latency":
            # Unseen deployments (no latency yet) sort first so they get sampled.
            return sorted(pool, key=lambda d: self._stat(d.id).latency_ewma or -1.0)
        return self._weighted_shuffle(pool)

    def _weighted_shuffle(self, pool: list[Deployment]) -> list[Deployment]:
        """Order by weighted random sampling without replacement."""
        remaining = list(pool)
        result: list[Deployment] = []
        while remaining:
            total = sum(d.weight for d in remaining)
            pick = random.uniform(0, total)
            upto = 0.0
            for d in remaining:
                upto += d.weight
                if pick <= upto:
                    result.append(d)
                    remaining.remove(d)
                    break
            else:  # pragma: no cover - float edge
                result.append(remaining.pop())
        return result

    # --- load-balancing stats -------------------------------------------------

    def _stat(self, dep_id: int) -> _Stats:
        return self._stats.setdefault(dep_id, _Stats())

    def note_start(self, dep_id: int) -> None:
        self._stat(dep_id).in_flight += 1

    def note_end(self, dep_id: int, latency_ms: float, ok: bool) -> None:
        stat = self._stat(dep_id)
        stat.in_flight = max(0, stat.in_flight - 1)
        if ok:
            prev = stat.latency_ewma
            stat.latency_ewma = latency_ms if prev is None else 0.7 * prev + 0.3 * latency_ms


# Process-wide singleton, shared via app.state.deployment_registry too.
registry = DeploymentRegistry()
