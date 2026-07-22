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
- ✅ Rate limiting: token bucket per key + model, `429` + `Retry-After` (memory or Redis)
- ✅ Resilience: retry with backoff, fail-over to fallback models, per-provider circuit breaker
- ✅ Exact-match cache: hash of the normalized request, per-tenant, `X-Cache: HIT/MISS` (memory or Redis)
- ✅ Observability: usage/cost ledger in the database, Prometheus `/metrics`, secret-redacting logs
- ✅ Hardened SSE (uniform error handling + anti-buffering headers), admin key CRUD, Docker deploy

Every request writes a usage record (tokens, estimated cost, latency, provider,
status, cache hit) off the hot path. `GET /admin/usage` returns totals and
`GET /metrics` exposes Prometheus counters/histograms.

Add a `fallbacks` list to any request and the gateway retries transient failures,
then fails over to the next model (possibly a different provider) if the primary
stays down:

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hello!"}],
  "fallbacks": ["claude-3-5-sonnet", "gemini-1.5-flash"]
}
```

Point any OpenAI SDK at the gateway and choose a provider purely by model name —
same request shape for all of them:

| Model prefix | Provider |
|---|---|
| `gpt-*` (default) | OpenAI |
| `gemini-*` | Google Gemini |
| `claude-*` | Anthropic |
| `azure/<deployment>` | Azure OpenAI |

## Admin endpoints

All require the `X-Admin-Token` header (set `ADMIN_API_KEY`).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/keys` | Create a virtual key (full key returned once) |
| `GET` | `/admin/keys` | List keys (prefix + metadata only) |
| `DELETE` | `/admin/keys/{id}` | Revoke a key (deactivates, keeps usage history) |
| `GET` | `/admin/usage` | Usage totals (requests, tokens, cost) |

## Deploy

The gateway is stateless — all state lives in Postgres and Redis — so it scales
horizontally behind a load balancer. `docker-compose` brings up the gateway with
both, wired to the Redis rate-limit/cache backends:

```bash
export ADMIN_API_KEY=your-admin-token
export OPENAI_API_KEY=sk-...        # and any other provider keys you use
docker compose up --build
```

`/health` is a readiness probe and `/metrics` is Prometheus-scrapeable.
