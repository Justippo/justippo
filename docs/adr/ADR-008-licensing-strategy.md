# ADR-008: Licensing Strategy — Open Core with AGPL-3.0 Dual License

**Date:** 2026-06-26
**Status:** Accepted
**Deciders:** Mihai Chindriș
**Supersedes:** ADR-008 (Proposed, 2026-06-03)
**Related:** ADR-012 (HTTP Boundary AGPL Isolation), ADR-006 (PDF Extraction License)

---

## Context

### Market Signal

MikeOSS (May 2026) — an AGPL-3.0 open-source alternative to Harvey/Legora — reached 3,600+ stars within weeks, proving that closed-source legal AI wrappers are not defensible. EvidenceEU is NOT a thin wrapper; it is a vertical document intelligence platform with a thick pipeline (OCR → layout-preserving translation → RAG → secure messaging across 27 EU jurisdictions).

### BabelDOC Factor

BabelDOC (AGPL-3.0) confirmed it cannot offer a commercial license ([funstory-ai/BabelDOC#595](https://github.com/funstory-ai/BabelDOC/issues/595) — closed). The submission and community edition use BabelDOC via HTTP sidecar — AGPL-compatible with our AGPL core.

### AGPL Open-Core Precedents (2024-2026)

| Project | Model | Outcome |
|---------|-------|---------|
| Grafana | AGPL-3.0 core + commercial enterprise | $6B+ valuation, thriving community |
| Nextcloud | AGPL-3.0 + enterprise subscriptions | Dominant in EU self-hosted market |
| Metabase | AGPL-3.0 + commercial embedding license | Successful dual-license |
| MongoDB | Was AGPL → moved to SSPL (over-correction) | AGPL phase was highly successful |

---

## Decision

### License Structure

| Component | License | Rationale |
|-----------|---------|-----------|
| Backend (`backend/`) | AGPL-3.0 | Copyleft prevents SaaS free-riding; compatible with BabelDOC |
| Frontend (`frontend/`) | MIT | Enables white-label/OEM embedding; UI is independent via HTTP |
| Proxy Worker (`worker/`) | AGPL-3.0 | Part of server-side stack; same rationale as backend |
| Documentation (`docs/`) | CC-BY-4.0 | Standard for docs; allows reuse with attribution |
| BabelDOC sidecar | AGPL-3.0 (upstream) | Isolated via HTTP boundary (ADR-012); no propagation |

### Translation Engine Strategy

| Context | Engine | Reason |
|---------|--------|--------|
| **Capstone submission** | BabelDOC sidecar (AGPL, HTTP-isolated) | Full layout-preserving translation; AGPL-compatible |
| **Text-only fallback** | CF Workers AI `m2m100-1.2b` | Pyodide-safe, free, for non-layout scenarios |
| **Community edition** | BabelDOC sidecar | Same as submission; no license friction |

### Contributor Agreement

**Capstone phase (now → Jul 2026):** DCO (Developer Certificate of Origin) via `Signed-off-by:` lines. All 4 team members are co-authors.

**Post-capstone (if external contributors):** Lightweight CLA (Apache ICLA model) granting dual-licensing rights. Required only when commercial license revenue is active.

### Commercial License (Phase 2, post-graduation)

Available for entities that cannot or will not comply with AGPL-3.0 obligations:
- Enterprise self-hosted (removes source-sharing obligation)
- White-label/OEM embedding (MIT frontend + commercial backend license)
- SLA + priority support tier

---

## HTTP Boundary Isolation (cross-reference: ADR-012)

BabelDOC runs as a separate Docker container communicating exclusively via HTTP POST. The AGPL's copyleft applies to derivative works (linked/compiled/imported code), NOT to independent programs communicating over a network API.

**Legal basis:**
- FSF GPL FAQ: "If the two programs communicate at arm's length [...] the modules are not combined into a larger program"
- AGPL Section 13 triggers source disclosure for *the AGPL program's own users*, not for callers of its HTTP API
- Industry precedent: Grafana (AGPL) calls non-AGPL data sources; Nextcloud (AGPL) integrates non-AGPL apps via HTTP

**Enforcement:**
- AST test (`test_babeldoc_adapter.py`): Fails if `babeldoc` is imported in `app/services/` or `app/api/`
- CI license audit (`.github/workflows/license-check.yml`): Copyleft deps flagged as warnings with documented justification
- ADR-012: Architectural documentation of the sidecar isolation principle

---

## EU AI Act Compliance Note

Article 13 (transparency obligations for high-risk AI systems) requires technical documentation and interpretability. Open-sourcing under AGPL **helps** satisfy these requirements by making the system inspectable. AGPL does NOT create additional AI Act obligations — it is a software license, not a regulatory framework.

EvidenceEU's classification: document translation/search is likely "limited risk" (Article 52 transparency obligations only), not "high risk." Full analysis deferred to a compliance-specific document.

---

## Consequences

### Positive

- Community contributions for 27 EU jurisdictions — impossible for 4 people alone
- BabelDOC AGPL compatibility (submission + community edition) — zero license friction
- Competitive moat — AGPL prevents SaaS cloning; domain expertise prevents shallow forks
- Investor-friendly — dual-license model proven by Grafana/MongoDB/Nextcloud
- EU AI Act alignment — open source aids transparency compliance

### Negative

- Some enterprises avoid AGPL on principle → commercial license addresses this
- Code visibility to competitors → moat is execution + domain expertise, not secret algorithms
- DCO/CLA adds minor contributor friction → acceptable trade-off for IP clarity

### Neutral

- Capstone grading: License choice has zero rubric impact
- No code changes required for the license switch (file-level changes only)

---

## Risk Table

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| 1 | Enterprise AGPL aversion delays adoption | Medium | Medium | Commercial license available; MIT frontend reduces concern |
| 2 | Fork competes as free hosted service | Low | High | AGPL forces fork to also be AGPL; we own brand + community |
| 3 | EU AI Act Art. 13 transparency burden | Low | Low | Open source helps compliance; no extra obligations from AGPL |
| 4 | CLA friction blocks future contributors | Medium | Low | DCO for now; CLA only when dual-license revenue justifies it |
| 5 | BabelDOC license propagation dispute | Very Low | High | HTTP boundary + AST test + CI check + ADR-012 |

---

## License CI Check

`.github/workflows/license-check.yml` — no changes needed:
- AGPL/GPL/LGPL: **warning** (non-blocking) — acceptable due to sidecar isolation
- SSPL/Proprietary: **hard fail** — cannot redistribute

---

## Implementation Checklist (Issue #46)

- [x] Replace root `LICENSE` with AGPL-3.0 text
- [x] Add `frontend/LICENSE` with MIT text
- [x] Add `LICENSES/AGPL-3.0-or-later.txt` (canonical reference)
- [x] Update README.md badge from MIT to AGPL-3.0
- [x] Update `sidecars/babeldoc/AGPL-NOTICE.md` (remove pending language)
- [x] Add `LICENSES/CC-BY-4.0.txt` for docs
- [x] Add CONTRIBUTING.md with DCO section
- [x] Add SPDX headers to source files (via `scripts/add_spdx_headers.sh`)
- [x] Close issue #42, unblock issue #46

---

## References

- [FSF: Fundamentals of AGPLv3](https://www.fsf.org/bulletin/2021/fall/the-fundamentals-of-the-agplv3)
- [FSF GPL FAQ: Mere Aggregation](https://www.gnu.org/licenses/gpl-faq.en.html#MereAggregation)
- [Grafana Licensing](https://grafana.com/licensing/) (AGPL-3.0 open core model)
- [MikeOSS](https://github.com/willchen96/mike) (AGPL-3.0 legal AI precedent)
- [BabelDOC#595](https://github.com/funstory-ai/BabelDOC/issues/595) (no commercial license)
- [EU AI Act Article 13](https://artificialintelligenceact.eu/article/13/) (transparency obligations)
- ADR-012: BabelDOC Sidecar Runtime (HTTP boundary architecture)
- ADR-006: PDF Extraction License (pypdfium2 Apache-2.0 decision)
