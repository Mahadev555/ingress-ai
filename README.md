# ingress-ai

Ingress AI is a standalone AI gateway that exposes one OpenAI-compatible API and
routes requests to multiple providers: OpenAI, Anthropic, Azure OpenAI, and Gemini.

It is built to stay small and readable while being production-shaped: shared
connection pools, streaming without buffering, and state kept in Redis + Postgres
so any replica can serve any request.

## Project layout

- `app/main.py` — FastAPI app, lifespan (shared HTTP client), route wiring
- `app/api/` — API endpoints for chat and admin
- `app/core/` — config, auth, rate limits, cache, and error handling
- `app/router/` — provider selection and health / circuit-breaker state
- `app/providers/` — adapter contract plus provider-specific translators
- `app/resilience/` — retry and fallback logic
- `app/schemas/` — unified request/response models and usage records
- `app/observability/` — logging, usage persistence, and metrics
- `app/db/` — Postgres models and async session setup

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Quickstart

```bash
# 1. Install dependencies into a local virtualenv
uv sync

# 2. Configure your OpenAI key
cp .env.example .env      # then edit .env and set OPENAI_API_KEY

# 3. Run the gateway
uv run uvicorn app.main:app --reload
```

Then call it exactly like the OpenAI API, pointing at the gateway's base URL:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Streaming works the same way — add `"stream": true` and the gateway relays the
server-sent events straight through without buffering.

## Virtual keys

Clients authenticate with a **virtual key** (`sk-ingress-…`) instead of a real
provider key — the provider keys stay server-side in config. Keys are stored
hashed (only a prefix is retained for display) and can be scoped to a set of
allowed models.

Set `ADMIN_API_KEY` in `.env`, then mint a key:

```bash
curl http://localhost:8000/admin/keys \
  -H "X-Admin-Token: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app", "allowed_models": ["gpt-4o-mini", "claude-3-5-sonnet"]}'
# -> {"id": 1, "key": "sk-ingress-...", ...}   (the full key is shown only once)
```

Use it as the bearer token on chat requests:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-ingress-..." \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## Tests

```bash
uv run pytest
```

## Status

- ✅ OpenAI-compatible `/v1/chat/completions` (streaming and non-streaming) + `/health`
- ✅ Canonical unified schema and a three-method provider adapter contract
- ✅ Four providers behind one API, routed by model name
- ✅ Virtual keys + auth: hashed keys, per-key allowed models, admin key management
- ⏳ Rate limiting, resilience, cache, observability

Point any OpenAI SDK at the gateway and choose a provider purely by model name —
same request shape for all of them:

| Model prefix | Provider |
|---|---|
| `gpt-*` (default) | OpenAI |
| `gemini-*` | Google Gemini |
| `claude-*` | Anthropic |
| `azure/<deployment>` | Azure OpenAI |
