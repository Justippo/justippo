CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,
    language        TEXT NOT NULL DEFAULT 'en',
    journey_type    TEXT,
    citizenship_group TEXT,
    jurisdiction    TEXT,
    message_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_active
    ON chat_sessions(is_active, updated_at);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_journey
    ON chat_sessions(journey_type, language);
