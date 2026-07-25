#!/usr/bin/env sh
# Timestamped backup of the local SQLite database into ./backups/ (git-ignored).
# Uses SQLite's own `.backup` (consistent even while the gateway is running);
# falls back to a file copy if the sqlite3 CLI isn't installed.
# Usage:  [DB_PATH=./ingress.db] sh scripts/backup_db.sh
set -eu

DB_PATH="${DB_PATH:-./ingress.db}"
OUT_DIR="${OUT_DIR:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$OUT_DIR/ingress.db.bak-$STAMP"

if [ ! -f "$DB_PATH" ]; then
  echo "error: no database at $DB_PATH (set DB_PATH if it lives elsewhere)." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$DEST'"
else
  echo "note: sqlite3 CLI not found; falling back to a plain file copy." >&2
  cp "$DB_PATH" "$DEST"
fi

echo "backed up $DB_PATH -> $DEST"
echo "reminder: this file holds real usage data — keep it out of git and away"
echo "from your CREDENTIAL_ENCRYPTION_KEY."
