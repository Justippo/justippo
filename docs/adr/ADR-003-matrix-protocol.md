# ADR-003: Secure Cross-Border Document Exchange — Matrix Protocol

**Date:** 2026-05-14
**Status:** Accepted (implementation deferred to Sprint 3)
**Author:** Mihai Chindriș

## Context

Cross-border document exchange requires end-to-end encryption, federated architecture (no central data broker), and GDPR-compliant data residency. Standard file-sharing (S3, Google Drive) centralizes data and creates GDPR exposure.

## Decision

Use the **Matrix protocol** for secure document exchange. Matrix provides:
- E2EE messaging (MegOlm/Olm encryption)
- Federated homeserver architecture — data stays in the originating country
- TI-Messenger compatibility (gematik-approved for German Telematikinfrastruktur)
- Audit trail via Matrix room event log (satisfies GDPR Article 30)

Implementation is a Sprint 3 placeholder (`ENABLE_MATRIX_EXCHANGE=false` feature flag).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Email with PGP | Poor UX, no structured document metadata |
| Signal Protocol | No federated homeserver; centralized |
| AWS S3 + presigned URLs | US data residency, GDPR risk for EU healthcare Phase 2 |
| IPFS | Immutability conflicts with GDPR right to erasure |

## Consequences

- Sprint 3 sets up a self-hosted Synapse homeserver (`evidenceeu.eu.mihai.codes`) with rate limits disabled, accessible via Cloudflare Tunnel
- TI-Messenger compatibility positions EvidenceEU for German healthcare Phase 2 without architectural changes
- The `exchange` API router and `ExchangePage` frontend are stubbed and feature-flagged
- Full E2EE implementation (key management, device verification) is out of capstone scope — demo uses basic Matrix room sharing

## References

- [ADR-018](ADR-018-matrix-authentication.md) — Matrix authentication (superseded by ADR-019)
- [ADR-019](ADR-019-matrix-oauth-pkce-authentication.md) — Matrix OAuth 2.0 PKCE authentication (complements this ADR)
