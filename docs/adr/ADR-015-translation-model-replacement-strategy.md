# ADR-015: Translation Model Replacement Strategy (Post-Capstone)

**Date:** 2026-07-08
**Status:** Proposed (post-capstone implementation)
**Updated:** 2026-07-08 — local Ollama inference resolves the cost concern (see Update below)
**Decider:** Mihai Chindriș (PO/Dev)
**Supersedes:** None (extends ADR-005 glossary terminology, ADR-012 BabelDOC sidecar)

## Context

EvidenceEU's MVP uses **m2m100-1.2b** (Meta, CC-BY-NC 4.0) as the cheap
translation tier on Cloudflare Workers AI. This was the correct choice for
the capstone:

- Only translation model available on CF Workers AI (Pyodide-safe, no sidecar)
- Free inference on CF edge (EU regions)
- Covers EN/DE/FR (the MVP's 3 languages)
- No data reaches Meta — model weights are open-source, inference runs on CF

However, two issues make m2m100 unsuitable for the **commercial phase**:

1. **License:** CC-BY-NC 4.0 (non-commercial only). The capstone is academic,
   but commercial deployment requires a replacement.
2. **Quality:** m2m100 is a 2021-era dedicated MT model. As of 2026, LLMs
   outperform dedicated MT models on translation benchmarks (see Research
   below). The Reddit r/MachineLearning consensus (2025): *"I don't recommend
   using NLLB-200 or M2M-100. They are quite resource-intensive and don't
   provide superior translation quality compared to LLMs."*

## Research (July 2026 web search)

### Dedicated MT models (m2m100's category)

| Model | Origin | License | EN-DE-FR | Verdict |
|-------|--------|---------|----------|---------|
| m2m100-1.2b | Meta (US) | CC-BY-NC 4.0 | ✅ | Current — non-commercial, superseded by LLMs |
| NLLB-200 | Meta (US) | CC-BY-NC 4.0 | ✅ | Same license issue, same quality ceiling |
| **Opus-MT** | Helsinki-NLP (Finland 🇫🇮) | Apache 2.0 | ✅ | Best European dedicated MT, but per-pair models (3 files for EN/DE/FR), requires sidecar |

### LLMs (SOTA for translation as of 2026)

| Model | Origin | License | EU languages | Verdict |
|-------|--------|---------|--------------|---------|
| **Apertus 8B** | SwissAI (Switzerland 🇨🇭) | Apache 2.0 | EN/DE/FR + 1000 | Already integrated for RAG; 90% translation benchmark score; can do translation via chat |
| **EuroLLM-22B** | EU-funded (🇪🇺) | Fully open | All 24 official EU languages | Strongest sovereign European LLM; 22B params (heavy); API availability TBD |
| TildeOpen LLM 30B | Tilde (Latvia 🇱🇻) | Open source | 34 European | 30B params — overkill for 3-language MVP |
| Mistral Large | Mistral AI (France 🇫🇷) | Commercial API | EN/FR/DE/ES/IT native | Already integrated as frontier tier; not open-weight |

### Key finding
The research consensus (2025-2026) is that **LLMs have surpassed dedicated MT
models** for translation quality. The post-capstone replacement for m2m100
should be an LLM, not another dedicated MT model.

## Decision

Replace m2m100 in **two phases**, both using LLMs (not dedicated MT models):

### Phase 1 (immediate post-capstone): Apertus 8B for translation

- **Already deployed** — no new infrastructure. Apertus is integrated for RAG
  answer generation via HuggingFace Router API.
- **European** (Swiss, Apache 2.0, sovereign)
- **90% translation benchmark score** (CSCS/Ticino test, Sept 2025)
- Add a `_call_apertus_translation()` method in `translation_service.py`,
  mirroring the existing `_call_mistral_large()` pattern.
- Update `MODEL_MAP`: cheap tier maps to Apertus instead of m2m100.
- **Risk:** Apertus 8B is slower than m2m100 (LLM chat vs dedicated MT).
  Acceptable for the cheap tier because Not Diamond routes simple/short text
  to it (fast) and complex text to Mistral Large (frontier).

### Phase 2 (medium-term): Evaluate EuroLLM-22B

- **Fully European sovereign** (EU-funded, all 24 official EU languages)
- 22B parameters — requires GPU hosting (not CF Workers AI)
- Wait for API availability (HuggingFace Router, Replicate, or self-host)
- If EuroLLM-22B proves viable: replace Apertus as the cheap tier, keeping
  Mistral Large as the frontier tier.
- If not viable: Apertus 8B remains the cheap tier (Phase 1 is sufficient).

### What we do NOT adopt

- **Opus-MT (Helsinki-NLP):** Best European *dedicated MT* model, but:
  - Requires a Docker sidecar (3rd sidecar alongside BabelDOC + Propella)
  - Per-language-pair models (3 files for EN/DE/FR vs Apertus's single model)
  - DRY violation: overlaps with BabelDOC's translation role
  - Dedicated MT is a dead-end category (LLMs have surpassed it)
  - **Only revisit if** LLM translation proves too slow/ expensive and a
    purpose-built MT model is needed for latency-critical paths.

- **NLLB-200:** Same license issue as m2m100 (CC-BY-NC), same quality ceiling.

- **TildeOpen LLM 30B:** Overkill for a 3-language MVP. Revisit if expanding
  to 34+ European languages.

## Consequences

### Positive
- **Commercial-ready:** Apertus (Apache 2.0) + Mistral Large (commercial API)
  have no license barriers.
- **European sovereignty:** Both translation models are European (Swiss + French).
- **No new infrastructure:** Phase 1 reuses the existing Apertus integration.
- **Quality improvement:** LLMs outperform m2m100 on legal/bureaucratic text.

### Negative
- **Latency:** Apertus 8B (LLM chat) is slower than m2m100 (dedicated MT REST).
  Mitigated by Not Diamond routing short/simple text to the cheap tier.
- **Cost:** Apertus via HuggingFace Router has per-token pricing (vs m2m100's
  free CF Workers AI tier). Budget impact: minimal for MVP volume.
- **Complexity:** Two LLM translation paths (Apertus + Mistral Large) vs one
  dedicated MT path (m2m100). Acceptable — both use the same `_call_*` pattern.

## Implementation checklist (post-capstone)

1. [ ] Add `_call_apertus_translation()` in `translation_service.py`
2. [ ] Update `MODEL_MAP` in `not_diamond.py`: cheap tier → Apertus
3. [ ] Remove m2m100 from `MODEL_MAP` and candidate lists
4. [ ] Update `_call_m2m100()` → rename to `_call_translation_model()` (DRY:
      one method dispatches to Apertus or Mistral Large based on routed model)
5. [ ] Re-run `train_not_diamond_router.py` to retrain the custom router with
      Apertus as the cheap tier (replaces m2m100 in the CSV)
6. [ ] Update `config.py`: remove `CF_WORKERS_AI_TRANSLATION_MODEL` (or keep
      as fallback only)
7. [ ] Update ADR-005 and config.py comments to reflect the new translation
      architecture
8. [ ] Monitor EuroLLM-22B API availability for Phase 2 evaluation

## Update (2026-07-08): Local Ollama Resolves Cost Concern

During implementation of the Not Diamond routing layer (Issue #71), we
discovered that HuggingFace Router API returns HTTP 402 (free credits
depleted) for Apertus 8B inference. The $0.10/month free tier is
insufficient for any real workload.

**Resolution:** Apertus 8B runs locally via Ollama on Apple Silicon
(M1 Max, 32GB RAM) using the Q4_K_M quantization (5.1GB, community GGUF
from `MichelRosselli/apertus`). This is free, unlimited, and produces
real translation quality scores.

**Training results (30 test cases, all real scores, zero errors):**
- m2m100: avg=0.542 (19/30 nonzero, best on 15/30)
- Apertus: avg=0.611 (22/30 nonzero, best on 19/30)
- Mistral Large: avg=0.811 (27/30 nonzero, best on 27/30)

This changes the "Negative consequences" section above:
- ~~Cost:~~ Apertus via local Ollama is **free** (no per-token pricing).
  The cost concern is resolved for local dev/CI. Production deployment
  would still need a hosted Apertus endpoint (HF Pro, self-hosted GPU,
  or Apertus.ai trial) — but that's a deployment concern, not a blocker.

The core decision (replace m2m100 with Apertus post-capstone) is
**strengthened** — Apertus outperforms m2m100 (0.611 vs 0.542) on
real translation quality data from EvidenceEU's own test cases.

## References

- Reddit r/MachineLearning (2025): LLMs surpass dedicated MT models —
  https://www.reddit.com/r/MachineLearning/comments/1i7wcrg/
- Apertus translation benchmark (CSCS, Sept 2025): 90% score —
  https://www.cscs.ch/science/computer-science-hpc/2026/apertus-powers-in-house-ai-translation-for-ticino
- EuroLLM-22B (EU-funded, 24 EU languages) —
  https://eurollm.io/ — https://openeurollm.eu/
- Helsinki-NLP/Opus-MT (Apache 2.0, Finnish) —
  https://github.com/Helsinki-NLP/Opus-MT
- TildeOpen LLM (30B, 34 European languages) —
  https://tilde.ai/tildeopen-llm/
- Existing ADRs: ADR-005 (glossary), ADR-012 (BabelDOC sidecar)
