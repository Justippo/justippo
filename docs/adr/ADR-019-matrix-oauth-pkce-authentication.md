# ADR-019: Matrix OAuth 2.0 Authentication with PKCE

**Date:** 2026-07-15
**Status:** Accepted — production rollout authorized 2026-07-15
**Decider:** Project team (Product Owner unavailable)
**Supersedes:** [ADR-018](ADR-018-matrix-authentication.md)
**Complements:** [ADR-003](ADR-003-matrix-protocol.md)

## Context

ADR-018 correctly identified Matrix as a potential identity authority, but its
protocol design was not valid. It treated `/_matrix/client/v3/login` as an OAuth
authorization endpoint, proposed a non-standard `/account/validate` endpoint,
and placed the Matrix access token in `localStorage`.

Matrix 1.15 introduced a distinct OAuth 2.0 authentication API. The OAuth and
legacy authentication APIs are mutually incompatible for a given access token,
and a homeserver may support either or both. EvidenceEU must therefore discover
OAuth support and endpoints instead of constructing endpoint URLs or silently
falling back to password login.

The rollout remains reversible through independent backend and frontend feature
flags. Matrix OAuth becomes the production login path once its deployment checks
pass.

## Decision

EvidenceEU will use the Matrix OAuth 2.0 **Authorization Code grant with PKCE
S256**, behind a backend-for-frontend session boundary.

### 1. Discovery is mandatory

The backend obtains authorization-server metadata from:

`GET {homeserver}/_matrix/client/v1/auth_metadata`

It uses the discovered `authorization_endpoint`, `token_endpoint`,
`revocation_endpoint`, `registration_endpoint`, supported response modes, and
account-management URI. A `404 M_UNRECOGNIZED` means OAuth is unavailable on
that homeserver. EvidenceEU fails closed with a neutral unavailable state; it
does not downgrade to the legacy password API or hardcoded credentials.

The target homeserver must be verified through discovery in the deployment
environment before OAuth authentication is enabled. `matrix.org` is a candidate,
not an assumed guarantee. **Actual deployment (capstone):** self-hosted Synapse
at `evidenceeu.eu.mihai.codes` with rate limits disabled, accessed via Cloudflare
Tunnel. OAuth discovery returns `unsupported` — demo mode bypasses OAuth using
`MATRIX_ACCESS_TOKEN` env var (see `backend/app/api/v1/endpoints/matrix_auth.py`).

### 2. EvidenceEU is an OAuth public client

EvidenceEU registers an OAuth client using the discovered dynamic registration
endpoint or uses deployment-provisioned registration metadata. Registration
uses a strict HTTPS callback URI and `token_endpoint_auth_method=none`; no client
secret is shipped to the browser.

The authorization request contains:

- `response_type=code`
- the registered `client_id` and exact `redirect_uri`
- a cryptographically random `state`
- PKCE `code_challenge` with `code_challenge_method=S256`
- `scope=urn:matrix:client:api:* urn:matrix:client:device:<device_id>`
- a response mode advertised by the discovered metadata

The callback rejects missing, expired, reused, or mismatched state. The backend
exchanges the code using the original `code_verifier` and exact redirect URI.

### 3. Tokens stay outside browser JavaScript

Matrix access and refresh tokens are never written to `localStorage`,
`sessionStorage`, URLs, logs, analytics, or client-readable cookies.

The backend stores short-lived session material in server-only Cloudflare D1,
which provides provider-managed encryption at rest, and returns only an opaque
EvidenceEU session identifier in a `Secure`, `HttpOnly` cookie. Production uses
`SameSite=None` because Pages and the API Worker are on different sites; local
same-site development uses `SameSite=Lax`.
D1 is not a user/password database: Matrix remains the identity authority and
EvidenceEU stores no passwords.

Session records must have an expiry and deletion path. Logs and observability
may contain only non-sensitive outcome metadata, never tokens, authorization
codes, PKCE verifiers, or raw user identifiers.

### 4. Identity, refresh, and logout follow the Matrix OAuth API

After token exchange, the backend calls:

`GET {homeserver}/_matrix/client/v3/account/whoami`

with the bearer access token to establish the Matrix user and device identity.
Expired access tokens are renewed through the discovered token endpoint using
the refresh-token grant. Logout revokes tokens through the discovered revocation
endpoint and deletes the EvidenceEU session.

Account registration, password recovery, and account management occur in the
homeserver-provided web UI. EvidenceEU links or redirects to discovered account
management capabilities instead of implementing password-management forms.

### 5. Feature gating and rollout

Authentication receives its own feature flag; it is not coupled to
`ENABLE_MATRIX_EXCHANGE`. Exchange can remain disabled while authentication is
evaluated, and authentication can fail closed without changing public search.

The hardcoded login is bypassed only after the OAuth flow, session restoration,
refresh, revocation, error states, and deployment configuration pass acceptance
tests. Backend and frontend flags remain independent rollback controls. A failed
OAuth capability or session check must fail closed.

## Consequences

### Positive

- User credentials are entered only in the homeserver-controlled UI.
- PKCE, strict redirects, state validation, refresh, and revocation follow the
  standardized Matrix OAuth flow.
- Matrix tokens are protected from routine browser-JavaScript access.
- Matrix remains the user store; D1 contains sessions, not accounts or passwords.
- Homeserver capability is verified rather than assumed.

### Negative

- Requires backend session handling and a small D1 session schema.
- Requires OAuth client registration and deployment-specific callback metadata.
- Authentication depends on homeserver OAuth availability and its web UI.
- Token refresh and revocation add failure modes that require explicit UX states.

### Neutral

- ADR-003 document exchange remains a separate capability.
- The existing login UI may become a neutral “Continue securely” entry point,
  while credential entry moves to the homeserver.
- This ADR does not authorize changes to GDPR middleware or consent handling.

## Implementation acceptance criteria

- [x] Project team authorizes rollout and selects Matrix.org using its
      delegated `matrix-client.matrix.org` client base URL.
- [x] Production discovery returns valid metadata with PKCE `S256` support.
- [x] OAuth client registration and exact HTTPS redirect URIs are configured.
- [x] State, PKCE verifier, and callback replay protections have automated tests.
- [x] Tokens never enter browser-readable storage, URLs, logs, or telemetry.
- [x] `/account/whoami` establishes identity after the code exchange.
- [ ] Refresh rotates tokens and safely handles `M_UNKNOWN_TOKEN`/soft logout.
- [x] Logout revokes tokens and deletes the EvidenceEU session.
- [ ] Signup, recovery, and account management use discovered homeserver UI.
- [ ] Hardcoded credentials and the boolean authentication flag are removed.
- [x] Authentication and Matrix exchange have independent feature flags.
- [ ] End-to-end tests cover success, denial, state mismatch, expiry, refresh,
      revocation, unavailable discovery, and session restoration.

## Rejected alternatives

| Alternative | Reason rejected |
|-------------|-----------------|
| Implement ADR-018 as written | Uses incorrect OAuth endpoints and exposes tokens to browser JavaScript |
| Legacy Matrix password login | Gives EvidenceEU direct access to user credentials and is incompatible with OAuth-issued tokens |
| OAuth tokens in `localStorage` | Increases token exposure during browser-script compromise |
| Assume `matrix.org` OAuth support | Matrix requires capability and endpoint discovery |
| Fall back silently to hardcoded login | Conceals authentication failure and preserves a non-production security path |
| Store EvidenceEU passwords in D1 | Duplicates the selected external identity authority |

## References

- [Matrix Client-Server API v1.19 — Client Authentication](https://spec.matrix.org/v1.19/client-server-api/#client-authentication)
- [Matrix Client-Server API v1.19 — OAuth 2.0 API](https://spec.matrix.org/v1.19/client-server-api/#oauth-20-api)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
