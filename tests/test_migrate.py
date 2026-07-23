"""The additive auto-migration adds missing columns without losing data."""

from sqlalchemy import inspect, text

from app.db.migrate import run_migrations
from app.db.session import create_engine


async def test_migration_adds_missing_columns_and_keeps_data():
    engine = create_engine("sqlite+aiosqlite:///:memory:")

    # Simulate a pre-upgrade DB: virtual_keys without the new policy columns,
    # plus one important row we must not lose.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE virtual_keys (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(128),
                    key_prefix VARCHAR(24),
                    key_hash VARCHAR(64),
                    tenant_id VARCHAR(64),
                    allowed_models JSON,
                    token_budget INTEGER,
                    active BOOLEAN,
                    created_at DATETIME
                )
                """
            )
        )
        await conn.execute(text("INSERT INTO virtual_keys (id, name) VALUES (1, 'keep-me')"))
        await conn.execute(
            text("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, key_id INTEGER)")
        )

    applied = await run_migrations(engine)
    assert "virtual_keys.tpm_limit" in applied
    assert "virtual_keys.budget_period" in applied
    assert "usage_records.trace_id" in applied

    def _cols(conn, table):
        return {c["name"] for c in inspect(conn).get_columns(table)}

    async with engine.begin() as conn:
        vk = await conn.run_sync(_cols, "virtual_keys")
        row = (await conn.execute(text("SELECT name FROM virtual_keys WHERE id=1"))).one()

    for col in ("rate_limit_per_minute", "cost_budget_usd", "budget_period", "tpm_limit",
                "max_concurrency", "expires_at", "last_used_at"):
        assert col in vk
    assert row[0] == "keep-me"  # data preserved

    # Running again is a no-op (idempotent).
    assert await run_migrations(engine) == []
    await engine.dispose()
