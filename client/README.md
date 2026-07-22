# Ingress AI — Gateway Console

A React + Vite + Tailwind dashboard for the Ingress AI gateway. It binds every
gateway API: virtual-key management, usage/cost, Prometheus metrics, health, and
an OpenAI-style chat playground with streaming.

## Run

```bash
cd client
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/v1`, `/admin`, `/health`, and `/metrics` to the gateway
at `http://localhost:8000` (override with `VITE_GATEWAY_URL`), so no CORS setup is
needed. Make sure the gateway is running:

```bash
# from the repo root
uv run uvicorn app.main:app --reload
```

## Configure

Open **Settings** in the app and set:

- **Admin token** — matches the gateway's `ADMIN_API_KEY` (unlocks Overview, Keys, Usage).
- **Virtual key** — a `sk-ingress-…` key (used by the Playground). Create one on the **API Keys** page.

Everything is stored in your browser's `localStorage`.

## Pages

| Page | Gateway APIs used |
|---|---|
| Overview | `GET /admin/usage`, `GET /admin/keys`, `GET /health` |
| API Keys | `GET/POST/DELETE /admin/keys` |
| Playground | `POST /v1/chat/completions` (streaming + non-streaming) |
| Usage | `GET /admin/usage`, `GET /metrics` |
| Settings | `GET /health`, `GET /admin/usage` (connection test) |

## Build

```bash
npm run build      # outputs to dist/
npm run preview
```
