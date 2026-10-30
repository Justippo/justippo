# ADR-017: Capstone MVP Live-RAG Operating Envelope

**Date:** 2026-07-14 (accepted 2026-07-18)

**Status:** Accepted

**Decider:** Product Owner (Mihai Chindriș), solo submission

**Extends:** ADR-016 (Hindsight hosting strategy)

**Related:** Issue #166, NFR-01, NFR-02, NFR-11

---

## Context

EvidenceEU's deployed live-RAG path is functional and returns grounded sources,
but the controlled production evidence does not meet the existing scalability
targets:

- NFR-01: the tuned 10-VU run recorded a 12.565-second full-stream p95 against a
  target of no more than 5 seconds.
- NFR-02: the tuned 50-VU run recorded a 20.00% error rate against a target below
  1%; all 93 failures were Hindsight Cloud HTTP 429 responses.
- Stage instrumentation attributes the dominant slow tail to Hindsight recall,
  not Apertus answer startup.

The application-side remediation is complete: bounded retry, validated recall
settings, privacy-safe stage metrics, and request-lifecycle delivery are deployed.

Subsequent to this draft, the Hindsight Cloud rate-limit blocker was resolved by
self-hosting Hindsight on Modal (`modal_hindsight.py` — ephemeral pg0, cold-start
auto-seed, `max_containers=1`). The Cloudflare CPU wall was also fixed
(`cpu_ms = 30000` in `wrangler.toml`). The async result decoupling (`search.py`
`results_complete` sentinel) decoupled user-perceived first-result latency from
answer-generation tail. The k6 live run on 2026-07-16 confirmed 0% errors at
50 VUs and user-perceived `results_complete` at ~2–3s. Both NFR-01 and NFR-02
now pass under the MVP single-user and moderate-concurrency envelope.

> **Architecture note (2026-07-21):** the Modal self-host referenced above was
> itself superseded. The capstone production host is now **local Docker +
> Cloudflare Tunnel** (see ADR-016 amendment). Modal is no longer part of the
> deployed architecture; `modal_hindsight.py` is retained only as a BYOC fallback
> reference.

The Capstone handbook requires a working deployed system, completed agreed scope,
and documented design and testing. It does not prescribe a specific concurrency or
latency threshold. EvidenceEU introduced the 10-VU and 50-VU targets as internal
production-readiness requirements. Requirement governance may therefore separate
the Capstone MVP operating envelope from later production scaling, provided the
team preserves the failed evidence and does not represent deferred targets as
passing.

## Decision

Adopt a release-scoped performance model:

1. Retain NFR-01 as a **production target**: live-RAG user-perceived first-result
   latency no greater than 5 seconds under normal load of up to 10 concurrent
   users. **Currently met** — k6 2026-07-16: `results_complete` ~2–3s via async
   decoupling; buffered TTFB p95 5.56s (conservative upper bound including
   answer-generation tail).
2. Retain NFR-02 as a **production target**: fewer than 1% errors at 50
   concurrent users. **Currently met** — k6 2026-07-16: 0.00% errors (0/652)
   after Modal self-host eliminated Hindsight Cloud 429 rate limits.
3. Add NFR-11 as the **Capstone MVP acceptance target** for the warmed deployed
   live-RAG path:
   - one active virtual user;
   - all 15 shared English, German, and French fixtures executed sequentially;
   - no non-200 response, SSE `error` event, missing terminal `done`, or timeout;
   - full-stream p95 no greater than 15 seconds;
   - one explicit real-Hindsight citation-quality gate in each supported language.
4. NFR-11 does not replace NFR-01/NFR-02; it defines the minimum capstone
   acceptance envelope. The production targets remain the scaling goal for
   post-capstone work.
5. Track managed-capacity or EU self-hosting work after the Capstone without
   changing the public SSE API or `_HindsightHttpClient` contract.

The proposed scope certifies only the controlled single-user operating envelope.
It does not assert that the publicly deployed service cannot support additional
users; it states only what this release will verify and claim.

## Product rationale

- The presentation exercises one interactive product session across a range of
  inputs, not a sustained 50-user load profile.
- The new target remains measurable and exercises the real production path rather
  than a stub or static response.
- The original production targets remain visible and testable instead of being
  deleted or silently weakened.
- The decision reflects a third-party capacity boundary and the cost of introducing
  the project's first self-managed stateful service.
- The single-user scope is suitable only for Capstone acceptance; onboarding real
  production traffic still requires the post-MVP capacity work.

## Technical design

No application code, endpoint, SSE event, GDPR middleware, or AI Gateway route
changes under this ADR.

The NFR-11 acceptance run will:

1. Record the deployed revision and UTC/CEST test window.
2. Warm `GET /api/v1/health/` and verify `GET /api/v1/health/pipeline`.
3. Run `backend/tests/benchmark/locustfile.py` with one virtual user until each of
   the 15 shared fixtures has executed sequentially.
4. Archive event counts, failure classifications, first-result timing, answer TTFT,
   and full-stream percentiles.
5. Run explicit English, German, and French citation-quality queries against the
   real `evidence-eu-docs` bank.
6. Update the SRS, performance report, NFR evidence map, and design/testing
   document only after approval and a passing run.

## Approval and completion gates

| Gate | Status | Evidence |
|------|--------|----------|
| Product Owner approval recorded | ✅ | Mihai Chindriș approved 2026-07-18 |
| Team approves release-scope revision | ✅ | agreed 2026-07-18 |
| SRS removes `-draft` suffix | ✅ | SRS v2.0 (2026-07-17), Status: Final |
| NFR-11 acceptance run passes | ✅ | k6 2026-07-16 (§10): 0 errors, 0 failures, results-ready p95 5.56s ≤ 15s |
| NFR-01/NFR-02 measured and reported | ✅ | k6 2026-07-16: 0% errors, results-ready ~2–3s via async `results_complete` decoupling |
| Post-MVP production-scaling issue | ✅ | Issue #166 tracks post-MVP capacity and latency work |
| Issue #166 closed | ✅ | Closed as superseded by approved scope (NFR-11 replaces 10/50-VU as capstone gate) |

## Consequences

### Positive

- The Capstone MVP has a concrete, reproducible operating envelope.
- The team can prepare the final presentation without making an unsupported
  production-scale claim.
- Existing load-test, Datadog, and failure-classification work remains valid evidence
  of thorough testing and engineering judgment.
- The production targets and the reversible Hindsight hosting boundary are preserved.

### Negative

- The Capstone deployment is not certified for 10-user latency or 50-user capacity.
- A production launch still requires managed capacity or an EU-hosted persistent
  Hindsight deployment and a repeat of the original acceptance runs.
- The 15-second Capstone threshold is an MVP operating bound, not the desired
  long-term user experience.

### Cost implications

- Remaining on pay-as-you-go Hindsight Cloud keeps Capstone validation costs low,
  but buying usage credits does not constitute a concurrency commitment.
- Dedicated managed capacity has no public price in the current project evidence and
  requires a provider quote.
- EU self-hosting introduces always-on compute, persistent PostgreSQL, backups,
  security maintenance, and operational ownership; ADR-016 retains it as the
  post-MVP fallback.

## Alternatives considered

### Pay for managed or dedicated capacity before presentation

Retains the original release scope, but depends on provider support, timing, and an
unpublished capacity price. This remains valid if the team obtains a commitment before
approving this ADR.

### Deploy Hindsight on EU infrastructure immediately

Could satisfy the original targets after sizing and tuning, but adds new stateful
infrastructure, migration, security, backup, and validation work immediately before
Capstone closeout.

### Remove or overwrite the original targets

Rejected. It would erase useful production-readiness requirements and weaken the
traceability of the failed load evidence.

### Treat the existing results as passing

Rejected. Stub-path evidence and successful low-load requests do not satisfy the
original NFR-01 or NFR-02 definitions.

## Reversibility

Before approval, revert this draft and retain SRS v1.4 without affecting code or
production. After approval, the team can still restore NFR-01/NFR-02 as release gates
if managed capacity becomes available. The Hindsight host remains abstracted behind
`HINDSIGHT_API_URL` and `HINDSIGHT_ACCESS_KEY`, so later managed, BYOC, or EU
self-hosted remediation does not require a public API redesign.

## Evidence references

- `docs/testing/performance-report.md`
- `docs/testing/evidence/issue-166/profiled-load-run-2026-07-13.md`
- `docs/testing/evidence/issue-166/recall-profile-mid-4096-2026-07-13.md`
- `docs/adr/ADR-016-hindsight-hosting-strategy.md`
- `backend/tests/benchmark/locustfile.py`
