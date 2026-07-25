# scripts/

Operational helpers for running and maintaining the gateway. Each script is
self-contained and reads its configuration from the environment so it works the
same locally and in CI/prod.

| Script | What it does |
|---|---|
| `smoke_test.sh` | Hit `/health`, `/v1/config`, `/v1/models` (and optionally one chat call) against a running gateway — a fast "is it alive and wired?" check. |
| `mint_key.sh` | Create a virtual key via the admin API and print it once. |
| `backup_db.sh` | Timestamped backup of the local SQLite DB into `backups/` (git-ignored). |

## Conventions

All scripts read these (with sensible defaults):

- `GATEWAY_URL` — base URL of the gateway (default `http://localhost:8000`)
- `ADMIN_TOKEN` — value for the `X-Admin-Token` header (falls back to `ADMIN_API_KEY`)

They're POSIX `sh` and run under Git Bash on Windows or any Unix shell:

```bash
GATEWAY_URL=http://localhost:8000 ADMIN_TOKEN=your-admin-token bash scripts/smoke_test.sh
```

> **Note:** `backups/` and any `*.db.bak-*` files are git-ignored on purpose — a
> SQLite backup contains real usage data (and must never be committed). Keep your
> `CREDENTIAL_ENCRYPTION_KEY` out of the same location as the backup, or the
> encrypted provider keys inside it become readable.
