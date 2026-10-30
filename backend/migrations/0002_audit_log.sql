CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    method          TEXT NOT NULL,
    path            TEXT NOT NULL,
    status_code     INTEGER NOT NULL,
    duration_ms     INTEGER,
    request_id_hash TEXT,
    mime_type       TEXT,
    target_lang     TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
    ON audit_log(timestamp);

CREATE INDEX IF NOT EXISTS idx_audit_log_path
    ON audit_log(path);
