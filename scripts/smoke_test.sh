#!/usr/bin/env sh
# Fast liveness + wiring check against a running gateway.
# Usage: GATEWAY_URL=http://localhost:8000 [CHAT_MODEL=gpt-4o-mini] sh scripts/smoke_test.sh
set -eu

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
get() { curl -fsS "$GATEWAY_URL$1"; }

say "1. Readiness  GET /health"
get /health && echo

say "2. Public config  GET /v1/config"
get /v1/config && echo

say "3. Advertised models  GET /v1/models"
get /v1/models && echo

# Optional end-to-end chat call. Needs a virtual key and a routable model.
# Provide both to exercise the full auth -> route -> provider path:
#   GATEWAY_URL=... VIRTUAL_KEY=sk-ingress-... CHAT_MODEL=gpt-4o-mini sh scripts/smoke_test.sh
if [ -n "${VIRTUAL_KEY:-}" ] && [ -n "${CHAT_MODEL:-}" ]; then
  say "4. Chat round-trip  POST /v1/chat/completions ($CHAT_MODEL)"
  curl -fsS "$GATEWAY_URL/v1/chat/completions" \
    -H "Authorization: Bearer $VIRTUAL_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}" \
    && echo
else
  say "4. Chat round-trip  SKIPPED (set VIRTUAL_KEY and CHAT_MODEL to run it)"
fi

say "Smoke test passed."
