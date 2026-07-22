from app.core.config import Settings
from app.providers.anthropic import AnthropicAdapter
from app.providers.azure_openai import AzureOpenAIAdapter
from app.providers.base import ProviderAdapter, ProviderCreds
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter

ADAPTERS: dict[str, ProviderAdapter] = {
    "openai": OpenAIAdapter(),
    "gemini": GeminiAdapter(),
    "anthropic": AnthropicAdapter(),
    "azure": AzureOpenAIAdapter(),
}

# Ordered (prefix, provider) rules. First match wins; unmatched models fall
# back to OpenAI, which keeps the gateway a transparent proxy by default.
MODEL_PREFIXES: list[tuple[str, str]] = [
    ("azure/", "azure"),
    ("gemini", "gemini"),
    ("claude", "anthropic"),
]

DEFAULT_PROVIDER = "openai"


def provider_for_model(model: str) -> str:
    for prefix, provider in MODEL_PREFIXES:
        if model.startswith(prefix):
            return provider
    return DEFAULT_PROVIDER


def creds_for_provider(provider: str, settings: Settings) -> ProviderCreds:
    if provider == "openai":
        return ProviderCreds(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    if provider == "gemini":
        return ProviderCreds(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url)
    if provider == "anthropic":
        return ProviderCreds(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            extra={"version": settings.anthropic_version},
        )
    if provider == "azure":
        return ProviderCreds(
            api_key=settings.azure_api_key,
            base_url=settings.azure_endpoint,
            extra={"api_version": settings.azure_api_version},
        )
    raise KeyError(f"no credentials configured for provider {provider!r}")


def resolve_model(model: str, settings: Settings) -> tuple[ProviderAdapter, ProviderCreds]:
    provider = provider_for_model(model)
    return ADAPTERS[provider], creds_for_provider(provider, settings)
