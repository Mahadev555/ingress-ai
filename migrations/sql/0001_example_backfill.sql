-- 0001_example_backfill.sql
-- Template for a Tier-2 (manual) migration. Safe to delete once you write a real one.
--
-- Tier-1 auto-migration (app/db/migrate.py) adds new columns as NULL. When a new
-- column needs a non-null default derived from existing data, do the ADD COLUMN in
-- Tier-1 and the data backfill here — applied deliberately, not on boot.
--
-- Dialect: SQLite + Postgres (this example is portable ANSI SQL).
-- Idempotent: re-running only touches rows still holding the placeholder value.

-- Example: default every existing key's budget_period to 'monthly' where it was
-- left at the additive-migration placeholder. Replace with your actual change.
UPDATE virtual_keys
SET budget_period = 'monthly'
WHERE budget_period = 'total'
  AND cost_budget_usd IS NOT NULL;

-- Verify (run manually, not part of the migration):
--   SELECT budget_period, COUNT(*) FROM virtual_keys GROUP BY budget_period;
