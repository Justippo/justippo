CREATE TABLE IF NOT EXISTS user_investigations (
    id              TEXT PRIMARY KEY,
    session_id      TEXT,
    topic           TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'en',
    summary         TEXT NOT NULL DEFAULT '',
    doc_ids         TEXT NOT NULL DEFAULT '[]',
    entity_mentions TEXT NOT NULL DEFAULT '[]',
    confidence      REAL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_investigations_topic
    ON user_investigations(topic);

CREATE INDEX IF NOT EXISTS idx_user_investigations_session
    ON user_investigations(session_id);
