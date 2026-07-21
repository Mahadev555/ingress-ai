from app.providers.openai import OpenAIAdapter

PROVIDER_REGISTRY = {
    "openai": OpenAIAdapter(),
}

def get_provider_adapter(provider: str):
    return PROVIDER_REGISTRY[provider]
