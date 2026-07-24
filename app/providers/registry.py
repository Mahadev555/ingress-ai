from app.core.config import Settings
from app.core.model_registry import registry as model_registry
from app.providers.anthropic import AnthropicAdapter
from app.providers.azure_openai import AzureOpenAIAdapter
from app.providers.base import ProviderAdapter, ProviderCreds
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter

# One OpenAI adapter instance is reused for every OpenAI-compatible provider —
# they share the exact wire format; only the base URL + key differ (per creds).
_openai = OpenAIAdapter()

ADAPTERS: dict[str, ProviderAdapter] = {
    "openai": _openai,
    "gemini": GeminiAdapter(),
    "anthropic": AnthropicAdapter(),
    "azure": AzureOpenAIAdapter(),
    # OpenAI-compatible providers — same adapter, different base URL + key.
    "groq": _openai,
    "together": _openai,
    "deepseek": _openai,
    "openrouter": _openai,
    "ollama": _openai,
}

# (base_url attr, api_key attr) on Settings for each OpenAI-compatible provider.
_COMPAT_SETTINGS: dict[str, tuple[str, str]] = {
    "openai": ("openai_base_url", "openai_api_key"),
    "groq": ("groq_base_url", "groq_api_key"),
    "together": ("together_base_url", "together_api_key"),
    "deepseek": ("deepseek_base_url", "deepseek_api_key"),
    "openrouter": ("openrouter_base_url", "openrouter_api_key"),
    "ollama": ("ollama_base_url", "ollama_api_key"),
}

# Ordered (prefix, provider) rules for models NOT in the DB registry. First match
# wins; unmatched models fall back to OpenAI, keeping the gateway a transparent
# proxy by default. Registered models resolve by their stored provider instead
# (see resolve_provider) — the compatible providers share non-prefixable model
# names like "llama-3.1-70b" or "deepseek-chat", so a prefix can't route them.
MODEL_PREFIXES: list[tuple[str, str]] = [
    ("azure/", "azure"),
    ("gemini", "gemini"),
    ("claude", "anthropic"),
]

DEFAULT_PROVIDER = "openai"


def provider_for_model(model: str) -> str:
    """Provider from the model *name* alone (prefix rules). Used only for models
    that aren't in the DB registry — prefer resolve_provider elsewhere."""
    for prefix, provider in MODEL_PREFIXES:
        if model.startswith(prefix):
            return provider
    return DEFAULT_PROVIDER


def resolve_provider(model: str) -> str:
    """The provider to route a model to: the DB registry's provider when the
    model is registered (authoritative — supports arbitrary names like
    "deepseek-chat"), otherwise the name-prefix fallback."""
    provider = model_registry.provider_of(model)
    if provider and provider in ADAPTERS:
        return provider
    return provider_for_model(model)


def creds_for_provider(provider: str, settings: Settings) -> ProviderCreds:
    if provider in _COMPAT_SETTINGS:
        base_attr, key_attr = _COMPAT_SETTINGS[provider]
        return ProviderCreds(
            api_key=getattr(settings, key_attr), base_url=getattr(settings, base_attr)
        )
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
    provider = resolve_provider(model)
    return ADAPTERS[provider], creds_for_provider(provider, settings)
