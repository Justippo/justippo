# Translation QA Domain Review

**Issue:** #20  
**Reviewer:** Mihai Chindriș  
**Date:** 2026-06-21  
**Scope:** EN/DE/FR legal and administrative document translation via the active m2m100 capstone path.

## Summary

The translation accuracy suite is ready for domain review and capstone evidence. It now contains 30 YAML-driven test cases covering legal terminology, administrative documents, table and numeric preservation, German compounds, false friends, multi-page consistency, glossary enforcement, and targeted German/French legal-admin stress cases.

The mock-based suite validates the test harness deterministically. Real m2m100 validation remains gated behind `TRANSLATION_INTEGRATION_TESTS=true` to avoid accidental Cloudflare Workers AI quota use.

## Review Additions

Added four domain-specific cases after review of German/French legal-admin risks:

| ID | Risk Area | Source → Target | Expected Behavior |
|----|-----------|-----------------|-------------------|
| TC-027 | German residence registration | DE→EN | `Meldebescheinigung` → `certificate of residence`; `Personalausweis` → `identity card` |
| TC-028 | German legal/admin certificates | DE→EN | `Handelsregisterauszug` → `commercial register extract`; `Führungszeugnis` → `certificate of good conduct` |
| TC-029 | German false friend | DE→EN | `Protokoll` in hearing context → `minutes`, not `protocol` |
| TC-030 | French false friend | FR→EN | `demande` in administrative context → `application`; no `demand` mistranslation |

## Quality Risks Identified

| Priority | Risk | Impact | Follow-up |
|----------|------|--------|-----------|
| P1 | Legal term drift for residence/work/civil-status vocabulary | Incorrect legal meaning in user-facing translation | Feed canonical terms into #32 glossary seed and translation-time hints |
| P1 | German compound decomposition errors | m2m100 may split or over-literalize administrative compounds | Keep TC-013, TC-014, TC-022, TC-025, TC-027, TC-028 in CI |
| P2 | False friends in DE/FR admin language | Looks fluent but legally wrong | Keep forbidden-term checks for `actual`, `action`, `bald`, `protocol`, `demand` |
| P2 | Table/header formatting loss | Document remains translated but harder to verify against original | Track as BabelDOC sidecar priority under #45 |
| P3 | Proper nouns and authorities | Authorities may be translated inconsistently | Add authority-name glossary rows as they appear in sample documents |

## Pass/Fail Method

The suite checks:

- `terminology`
- `completeness`
- `structural_preservation`
- `table_integrity`
- `consistency`
- `numeric_preservation`
- `no_forbidden_terms`
- `glossary_enforcement`

Mock tests pass when expected target terms appear, forbidden terms are absent, pages are preserved, numbers survive, and repeated terms are translated consistently.

Real-model failures are classified by the runner as:

- `SERVICE_BUG` — translation service raised an exception.
- `MODEL_LIMITATION` — m2m100 produced output but missed expected terms or included forbidden terms.
- `TEST_CASE_STALE` — source term leaked into output, suggesting either stale expected terms or model non-translation.

## Documentation Feed-through

- **Glossary #32:** Added cases map directly to glossary seed candidates and translation-time hint priorities.
- **Design & Testing #27:** Translation QA evidence now reflects 30 cases and real-model gating rather than mock-only status.
- **Security/GDPR:** Translation processing remains ephemeral; no translated document content is persisted by the test suite.

## Real Model Validation

Real m2m100 execution is intentionally opt-in:

```bash
export TRANSLATION_INTEGRATION_TESTS=true
export TRANSLATION_TEST_DELAY_S=0.5
cd backend && uv run pytest tests/integration/test_translation_accuracy.py -v -k RealModel
```

Do not enable this by default in CI because it consumes Workers AI quota and requires live Cloudflare credentials.
