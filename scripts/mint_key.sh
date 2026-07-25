#!/usr/bin/env sh
# Create a virtual key via the admin API and print it (shown only once).
# Usage:
#   ADMIN_TOKEN=... sh scripts/mint_key.sh "my-app" "gpt-4o-mini,claude-3-5-sonnet"
# Args:
#   $1  key name           (default: "cli-key")
#   $2  allowed models CSV (optional; omit to allow all)
set -eu

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-${ADMIN_API_KEY:-}}"
NAME="${1:-cli-key}"
MODELS_CSV="${2:-}"

if [ -z "$ADMIN_TOKEN" ]; then
  echo "error: set ADMIN_TOKEN (or ADMIN_API_KEY) to your admin token." >&2
  exit 1
fi

# Build the allowed_models JSON array from the CSV, or null for "all".
if [ -n "$MODELS_CSV" ]; then
  MODELS_JSON=$(printf '%s' "$MODELS_CSV" | awk -F',' '{
    printf "["
    for (i = 1; i <= NF; i++) { printf "%s\"%s\"", (i > 1 ? "," : ""), $i }
    printf "]"
  }')
else
  MODELS_JSON="null"
fi

curl -fsS "$GATEWAY_URL/admin/keys" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$NAME\",\"allowed_models\":$MODELS_JSON}"
echo
