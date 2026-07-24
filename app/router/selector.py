from dataclasses import dataclass
from typing import Optional

from app.core.config import Settings
from app.providers.base import ProviderAdapter, ProviderCreds
from app.providers.registry import (
    ADAPTERS,
    creds_for_provider,
    provider_for_model,
    resolve_model,
)
from app.router.deployments import Deployment, DeploymentRegistry


@dataclass
class Candidate:
    provider: str
    model: str  # public name — used for accounting/pricing
    adapter: ProviderAdapter
    creds: ProviderCreds
    # Set when this candidate came from a load-balanced deployment, so the
    # router can attribute latency/in-flight stats back to it.
    deployment_id: Optional[int] = None
    # Provider-side name to send upstream (e.g. Azure deployment name). None =
    # use `model`. Lets one public model fan out to differently-named backends.
    upstream_model: Optional[str] = None

    @property
    def wire_model(self) -> str:
        """The model name actually sent to the provider."""
        return self.upstream_model or self.model


def _creds_from_deployment(dep: Deployment, settings: Settings) -> ProviderCreds:
    """A deployment supplies its own key (and optional endpoint), but inherits
    the provider's default base URL and extras (e.g. Anthropic version)."""
    base = creds_for_provider(dep.provider, settings)
    return ProviderCreds(
        api_key=dep.api_key,
        base_url=dep.base_url or base.base_url,
        extra=base.extra,
    )


def build_candidates(
    model: str,
    fallbacks: list[str],
    settings: Settings,
    deployments: Optional[DeploymentRegistry] = None,
    strategy: str = "simple-shuffle",
) -> list[Candidate]:
    """Ordered provider+model chain to try: the requested model first, then any
    fallback models. Each entry re-enters the registry, so a fallback can be a
    different provider entirely. Duplicates are dropped, order preserved.

    When the deployment registry has entries for a model, that model expands into
    one candidate per healthy deployment, ordered by the load-balancing strategy
    — so a single model name spreads across several keys, and a failed key fails
    over to the next. Otherwise a model resolves to its single env credential.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()

    for candidate_model in [model, *fallbacks]:
        if candidate_model in seen:
            continue
        seen.add(candidate_model)

        if deployments is not None and deployments.has(candidate_model):
            for dep in deployments.ordered(candidate_model, strategy):
                candidates.append(
                    Candidate(
                        provider=dep.provider,
                        model=candidate_model,
                        adapter=ADAPTERS[dep.provider],
                        creds=_creds_from_deployment(dep, settings),
                        deployment_id=dep.id,
                        upstream_model=dep.upstream_model,
                    )
                )
            continue

        adapter, creds = resolve_model(candidate_model, settings)
        candidates.append(
            Candidate(
                provider=provider_for_model(candidate_model),
                model=candidate_model,
                adapter=adapter,
                creds=creds,
            )
        )

    return candidates
