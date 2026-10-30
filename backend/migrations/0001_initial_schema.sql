CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    mime_type   TEXT NOT NULL,
    page_count  INTEGER NOT NULL DEFAULT 0,
    detected_language TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'processed',
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);

CREATE TABLE IF NOT EXISTS translation_jobs (
    job_id          TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    error           TEXT,
    output_key      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translation_pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (job_id) REFERENCES translation_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_translation_jobs_document_id
    ON translation_jobs(document_id);

CREATE INDEX IF NOT EXISTS idx_translation_jobs_status
    ON translation_jobs(status);

CREATE INDEX IF NOT EXISTS idx_translation_pages_job_id
    ON translation_pages(job_id);
