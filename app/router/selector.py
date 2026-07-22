from dataclasses import dataclass

from app.core.config import Settings
from app.providers.base import ProviderAdapter, ProviderCreds
from app.providers.registry import creds_for_provider, provider_for_model, resolve_model


@dataclass
class Candidate:
    provider: str
    model: str
    adapter: ProviderAdapter
    creds: ProviderCreds


def build_candidates(
    model: str, fallbacks: list[str], settings: Settings
) -> list[Candidate]:
    """Ordered provider+model chain to try: the requested model first, then any
    fallback models. Each entry re-enters the registry, so a fallback can be a
    different provider entirely. Duplicates are dropped, order preserved.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()

    for candidate_model in [model, *fallbacks]:
        if candidate_model in seen:
            continue
        seen.add(candidate_model)
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
