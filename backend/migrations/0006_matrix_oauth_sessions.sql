-- ADR-019: short-lived OAuth transaction and session storage.
-- Matrix remains the identity authority; this is not a user/password database.

CREATE TABLE IF NOT EXISTS matrix_oauth_states (
    state_hash TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    device_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS matrix_oauth_sessions (
    session_id TEXT PRIMARY KEY,
    matrix_user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT NOT NULL DEFAULT 'Bearer',
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matrix_oauth_states_expiry
    ON matrix_oauth_states(expires_at);

CREATE INDEX IF NOT EXISTS idx_matrix_oauth_sessions_expiry
    ON matrix_oauth_sessions(expires_at);
