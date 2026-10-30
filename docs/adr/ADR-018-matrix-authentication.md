# ADR-018: Matrix Authentication

**Date:** 2026-07-14
**Status:** Superseded by [ADR-019](ADR-019-matrix-oauth-pkce-authentication.md)
**Decider:** Mihai Chindriș (PO/Dev)
**Supersedes:** None (complements ADR-003 Matrix protocol for document exchange)

> This decision must not be implemented. It conflates the legacy Matrix login API
> with the Matrix OAuth 2.0 API, names a non-standard token-validation endpoint,
> and would expose access tokens to browser JavaScript. ADR-019 replaces it with a
> discovery-driven OAuth 2.0 Authorization Code + PKCE decision.

## Context

EvidenceEU's login page currently uses hardcoded credentials (`test@test.com` / `test123`) with `localStorage` for session persistence. There is no backend authentication, no user database, and no real signup flow. The app needs a real authentication mechanism for the demo and submission.

The team considered adding a database (Cloudflare D1 or external free tier) to manage user accounts. However, the project already uses Matrix for secure document exchange (ADR-003), and the Matrix homeserver (`matrix.org`) handles user accounts, password hashing, and session management as part of the protocol. A separate database would duplicate what Matrix already provides.

## Decision

Use the **Matrix protocol for authentication**. The `matrix.org` homeserver acts as the user store — no separate database is needed.

The login flow:

1. User enters credentials on the login page
2. Frontend calls `matrix.org`'s `/_matrix/client/v3/login` endpoint
3. `matrix.org` validates credentials and returns an access token
4. Frontend stores the access token in `localStorage`
5. Backend verifies the token via `/_matrix/client/v3/account/validate` before processing requests

For the demo, we register one test user on `matrix.org` (e.g., `evidenceeu-demo:matrix.org`).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Cloudflare D1 user table | Overkill for single-user demo; duplicates what Matrix provides; adds DB maintenance burden |
| External free-tier DB (Supabase, PlanetScale) | Introduces an external dependency for a problem Matrix already solves |
| Keep hardcoded demo login | Not suitable for submission; no real auth flow; doesn't demonstrate Matrix integration |

## Consequences

### Positive
- **No database needed:** `matrix.org` stores user accounts, password hashes, and sessions
- **Unified protocol:** Same Matrix protocol handles both authentication and document exchange (ADR-003)
- **Real auth flow:** Actual credential validation, token-based sessions, proper signup via Matrix registration API
- **Zero backend auth code:** No JWT creation, no password hashing, no session management — Matrix handles it all

### Negative
- **Homeserver dependency:** Auth availability depends on `matrix.org` uptime (acceptable for demo; production could use a self-hosted homeserver)
- **Privacy vs anonymity:** `matrix.org` sees user IP addresses and metadata (who talks to whom), though message content remains E2EE-encrypted

### Neutral
- Current hardcoded demo credentials must be replaced with real Matrix user registration
- Login page UI remains the same; only the backend call changes

## Implementation checklist

1. [ ] Register test user on `matrix.org` (e.g., `evidenceeu-demo:matrix.org`)
2. [ ] Replace hardcoded login with Matrix `/_matrix/client/v3/login` call
3. [ ] Store Matrix access token in `localStorage` (replaces `"true"` flag)
4. [ ] Add backend token verification against `matrix.org`
5. [ ] Remove signup and forgot password pages (Matrix handles account management)
6. [ ] Update `ENABLE_MATRIX_EXCHANGE` feature flag scope to include auth

## References

- [ADR-003](ADR-003-matrix-protocol.md) — Matrix protocol for document exchange
- Matrix Client-Server API: https://spec.matrix.org/latest/client-server-api/
