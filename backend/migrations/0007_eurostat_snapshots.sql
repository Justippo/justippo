-- Eurostat migration statistics cache (issue #232)
-- Stores JSON snapshots from the Eurostat Statistics API with a TTL.
-- The dataset (migr_pop1ctz) is updated annually, so a 24h TTL is generous.

CREATE TABLE IF NOT EXISTS eurostat_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_code  TEXT NOT NULL DEFAULT 'migr_pop1ctz',
    data_json     TEXT NOT NULL,
    fetched_at    INTEGER NOT NULL,
    ttl_seconds   INTEGER NOT NULL DEFAULT 86400
);

CREATE INDEX IF NOT EXISTS idx_eurostat_snapshots_dataset
    ON eurostat_snapshots(dataset_code);

CREATE INDEX IF NOT EXISTS idx_eurostat_snapshots_fetched_at
    ON eurostat_snapshots(fetched_at);