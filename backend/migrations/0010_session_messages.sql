CREATE TABLE IF NOT EXISTS session_messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content_summary TEXT NOT NULL DEFAULT '',
    content_length  INTEGER NOT NULL DEFAULT 0,
    has_citations   INTEGER NOT NULL DEFAULT 0,
    grounding_verdict TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session
    ON session_messages(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_session_messages_role
    ON session_messages(session_id, role);
