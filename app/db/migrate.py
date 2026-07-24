"""Tiny additive auto-migration.

This project has no migration tool, so on startup we reconcile existing tables
with the current models by adding any missing columns in place — preserving all
data. New *tables* are handled by ``create_all``; this covers new *columns* on
tables that already exist (e.g. the per-key policy fields added later).

Additive only: it never drops or alters existing columns. For production
Postgres you'd graduate to Alembic; this keeps local SQLite upgrades painless.
"""

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine


def _additive_columns(dialect: str) -> dict[str, dict[str, str]]:
    ts = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    json_type = "JSONB" if dialect == "postgresql" else "JSON"
    return {
        "virtual_keys": {
            "rate_limit_per_minute": "INTEGER",
            "cost_budget_usd": "FLOAT",
            "budget_period": "VARCHAR(16) NOT NULL DEFAULT 'total'",
            "tpm_limit": "INTEGER",
            "max_concurrency": "INTEGER",
            "expires_at": ts,
            "last_used_at": ts,
            "team_id": "INTEGER",
            "tags": json_type,
        },
        "usage_records": {
            "trace_id": "VARCHAR(36)",
            "tags": json_type,
        },
        "audit_logs": {
            "conversation_id": "VARCHAR(64)",
        },
        # Deployments moved from carrying their own key to referencing a
        # provider credential (provider_credentials is a new table via create_all).
        "model_deployments": {
            "credential_id": "INTEGER",
            "upstream_model": "VARCHAR(128)",
        },
    }


def _sync(conn, columns: dict[str, dict[str, str]]) -> list[str]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    applied: list[str] = []
    for table, wanted in columns.items():
        if table not in tables:
            continue  # brand-new DB: create_all already made it with all columns
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in wanted.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                applied.append(f"{table}.{name}")
    return applied


async def run_migrations(engine: AsyncEngine) -> list[str]:
    """Add any missing columns to existing tables. Returns what it applied."""
    columns = _additive_columns(engine.dialect.name)
    async with engine.begin() as conn:
        return await conn.run_sync(_sync, columns)
