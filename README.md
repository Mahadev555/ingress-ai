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

## Tests

```bash
uv run pytest
```

## Status

- ✅ OpenAI-compatible `/v1/chat/completions` (streaming and non-streaming) + `/health`
- ✅ Canonical unified schema and a three-method provider adapter contract
- ✅ Four providers behind one API, routed by model name
- ⏳ Virtual keys, rate limiting, resilience, cache, observability

Point any OpenAI SDK at the gateway and choose a provider purely by model name —
same request shape for all of them:

| Model prefix | Provider |
|---|---|
| `gpt-*` (default) | OpenAI |
| `gemini-*` | Google Gemini |
| `claude-*` | Anthropic |
| `azure/<deployment>` | Azure OpenAI |
