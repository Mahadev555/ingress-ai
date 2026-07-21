# ingress-ai
Ingress AI is a standalone AI gateway that exposes one OpenAI-compatible API and routes requests to multiple providers: OpenAI, Anthropic, Azure OpenAI, and Gemini.

The architecture is modular:
- `app/main.py`: FastAPI app and route wiring
- `app/api/`: API endpoints for chat and admin
- `app/core/`: auth, rate limits, cache, and error handling
- `app/router/`: provider selection and health/circuit breaker state
- `app/providers/`: adapter contract plus provider-specific translators
- `app/resilience/`: retry and fallback logic
- `app/schemas/`: unified request/response models and usage records
- `app/observability/`: logging, usage persistence, and metrics
- `app/db/`: Postgres models and async session setup

This skeleton is designed for production-ready routing, streaming, and horizontal scaling with Redis + Postgres state.