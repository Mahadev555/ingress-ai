# migrations/

Schema evolution for the gateway. The project uses a **two-tier** approach so
that the common case stays zero-effort while destructive changes have a safe home.

## Tier 1 — automatic, additive (in code)

On startup, [`app/db/migrate.py`](../app/db/migrate.py) reconciles existing tables
with the current models: new **tables** are created by `create_all`, and new
**columns** on existing tables are added in place (`ALTER TABLE ... ADD COLUMN`),
preserving all data. This is dialect-aware (SQLite and Postgres) and runs on every
boot.

**When it's enough:** adding a nullable column, a new table, a new index-free
field. Just add the model attribute and (for a column on an existing table) an
entry in `_additive_columns()`.

**What it will NOT do** — by design, it never drops or rewrites existing schema:

- rename or drop a column / table
- change a column's type or nullability
- backfill or transform existing rows
- add a constraint that existing data might violate

## Tier 2 — manual SQL (this folder)

Anything in the "will not do" list above goes here as a numbered, hand-written
migration you apply deliberately — never automatically on boot.

```
migrations/
  README.md
  sql/
    0001_example_backfill.sql   ← template; safe to delete
```

Naming: `NNNN_short_description.sql`, zero-padded and monotonically increasing.
Each file should be idempotent where practical and note whether it targets SQLite,
Postgres, or both.

Apply one manually:

```bash
# SQLite (local dev)
sqlite3 ./ingress.db < migrations/sql/0001_example_backfill.sql

# Postgres (prod) — always back up first
psql "$DATABASE_URL" -f migrations/sql/0001_example_backfill.sql
```

> **Always** run `scripts/backup_db.sh` (or a `pg_dump`) before applying a Tier-2
> migration in an environment with real data.

## Graduating to Alembic

When Tier-1 auto-migration stops being enough day-to-day (frequent destructive
changes, multiple environments to keep in lock-step), replace both tiers with
[Alembic](https://alembic.sqlalchemy.org/): `uv add alembic`, `alembic init
migrations`, point `env.py` at `app.db.models.Base.metadata`, and generate
versioned migrations here instead. Until then, the two-tier approach keeps local
upgrades painless without the extra dependency.
