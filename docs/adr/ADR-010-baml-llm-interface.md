# ADR-010: BAML as Type-Safe LLM Generation Interface

**Date:** 2026-06-13
**Status:** Accepted
**Deciders:** Mihai Chindriș
**Context:** Sprint 2 — first LLM generation call needed for the domain glossary (ADR-005); AdalFlow experiment exists for offline prompt optimization
**See also:** [ADR-005](ADR-005-glossary-terminology.md) — Domain glossary, [ADR-007](ADR-007-memory-rag-layer.md) — Single-vendor discipline

---

## TL;DR

**BAML** (Boundary ML's type-safe LLM function language) is adopted as the **runtime generation interface** for EvidenceEU's typed LLM calls. It is used for exactly one call today — the glossary extraction (`prompt → typed GlossaryTerm[]` output). The other three service calls (OCR, translation, retrieval) do **not** use BAML because they are either non-LLM API calls or do not require structured output parsing. **AdalFlow** is restricted to offline prompt discovery/optimization — never wired into production request paths.

---

## Context

### The Trigger: Domain Glossary Extraction

EvidenceEU's first prompt-to-typed-output call is the domain glossary extractor from [ADR-005](ADR-005-glossary-terminology.md): given a document text chunk (EN/DE/FR), return a typed list of `GlossaryTerm` objects with canonical forms in all three languages plus legal definitions.

Three approaches were evaluated:

| Approach | Mechanism | Risk |
|----------|-----------|------|
| **Manual JSON prompt + `json.loads()`** | System prompt asking for JSON; parse raw string | No schema enforcement; silent parse failures; prompt bleeds into Python code |
| **Instructor / Pydantic-only** | Pydantic models + Instructor's `response_model` | Tight coupling to OpenAI client; no cross-provider schema portability |
| **BAML** | Define function signature + prompt in a `.baml` DSL; generate typed Python clients | New DSL to learn; generated code committed to repo |

BAML was chosen because glossary extraction is a **PROMPT → TYPED-OUTPUT** call — BAML's core design space. The compiler generates:
- `backend/baml_client/types.py` — Pydantic models (`GlossaryTerm` with `term_en`, `term_de`, `term_fr`, `definition`)
- `backend/baml_client/sync_client.py` — type-safe function `b.ExtractGlossaryTerms(text: str, source_lang: str) -> List[GlossaryTerm]`
- `backend/baml_client/async_client.py` — async variant for future use

The prompt lives in `backend/baml_src/glossary.baml`, separate from Python code — clean separation of prompt engineering from business logic.

### Why the Other 3 Calls Don't Use BAML

EvidenceEU has four backend service calls. Exactly one is a prompt-to-typed-output pattern:

| Call | Service File | Pattern | Uses BAML? | Why Not |
|------|-------------|---------|------------|---------|
| **Glossary extraction** | `backend/app/services/glossary_service.py` | Prompt → typed `GlossaryTerm[]` | ✅ Yes | BAML's sweet spot |
| **OCR** | `backend/app/services/ocr_service.py` | API call → Mistral OCR / Tesseract | ❌ No | Document processing API, not LLM generation. Bytes in → text out. No prompt, no structured output to parse. |
| **Translation** | `backend/app/services/translation_service.py` | HTTP call → CF Workers AI `m2m100-1.2b` | ❌ No | Direct HTTP request to a specialized translation model (not chat completions). The `_call_m2m100()` method sends a raw JSON body and receives a plain string — no typed schema needed. |
| **RAG retrieval** | `backend/app/services/rag_service.py` | Vector search → Hindsight hybrid | ❌ No | Database query (semantic + BM25 + graph + temporal), not an LLM call. No prompt, no generation, no output parsing. |

**Decision rule:** BAML is used when (a) an LLM processes a prompt AND (b) produces structured output that must be parsed into typed Python objects. Only the glossary call meets both criteria today.

### The AdalFlow Dimension

An [AdalFlow](https://github.com/SylphAI-Inc/AdalFlow) Text-Grad prompt optimization experiment exists at `experiments/adalflow/rag_recall_opt.py`. AdalFlow uses LLM feedback as gradients to automatically optimize prompts through textual differentiation — a form of **AutoDiff for text**.

**AdalFlow is strictly offline.** It lives in `experiments/adalflow/` with its own isolated `requirements.txt` (`adalflow>=0.2.0`, `openai>=1.0.0` — separate from `backend/pyproject.toml`). No production module imports it. Its purpose is prompt discovery:

1. Load a seed eval set (20 multilingual RAG queries)
2. Define a trainable `MultilingualRAGRecall` component with `Parameter(requires_opt=True)` on the synthesis prompt
3. Run `Trainer.fit()` → Text-Grad backprop → optimized prompt
4. Save to `experiments/adalflow/optimized_prompt.json`

A developer then manually copies the optimized prompt into the appropriate `.baml` file. AdalFlow never touches the hot path.

---

## Decision

1. **BAML is the type-safe LLM generation interface for runtime calls.** All future prompt→typed-output calls must go through BAML.

2. **The glossary extraction call is the first (and currently only) BAML call.** Defined across:
   - `backend/baml_src/glossary.baml` — function signature, prompt, output schema
   - `backend/baml_src/clients.baml` — named client `CFGateway` routing through CF AI Gateway
   - `backend/app/services/glossary_service.py` — business logic wrapper with validation + lazy client init
   - `backend/app/integrations/baml_setup.py` — env var injection for CF AI Gateway routing

3. **All BAML calls route through Cloudflare AI Gateway (REM-8).** The `CFGateway` named client uses `provider "openai"` with `base_url` pointing to CF AI Gateway's `/compat` endpoint. The `api_key` is the Cloudflare API Token — never a direct provider key. Env vars are injected by `backend/app/integrations/baml_setup.py` before the `baml_client` import.

4. **OCR, translation, and retrieval do NOT use BAML.** They are not prompt→typed-output calls. Forcing BAML onto them would add indirection with zero benefit.

5. **AdalFlow is for offline prompt optimization only.** It lives in `experiments/adalflow/`, has its own isolated dependencies, and is never imported by production code.

---

## Appendix A: AdalFlow / BAML Workflow Split

```
┌─────────────────────────────────────────────────────────────────┐
│                    OFFLINE (experiment)                          │
│                                                                  │
│  experiments/adalflow/rag_recall_opt.py                          │
│    │                                                             │
│    ├─ Load eval set (20 multilingual queries)                    │
│    ├─ Define trainable RAG component with Parameter(prompt)      │
│    ├─ Trainer.fit() → Text-Grad optimization                    │
│    ├─ Save to experiments/adalflow/optimized_prompt.json         │
│    │                                                             │
│    └─ Developer manually copies optimized prompt into:           │
│         ├─ backend/baml_src/glossary.baml  (if glossary)         │
│         └─ service code (if RAG synthesis, future Sprint 3)     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    RUNTIME (production)                           │
│                                                                  │
│  POST /api/v1/documents/                                         │
│    │                                                             │
│    ├─ OCR: ocr_service.py → Mistral / Tesseract API              │
│    │   (no BAML — not an LLM generation call)                    │
│    │                                                             │
│    ├─ Translation: translation_service.py → CF m2m100-1.2b       │
│    │   (no BAML — raw HTTP call, plain text output)              │
│    │                                                             │
│    ├─ Glossary: glossary_service.py → BAML → CF Gateway          │
│    │   ┌──────────────────────────────────────────┐              │
│    │   │ baml_client.sync_client.b                 │              │
│    │   │   .ExtractGlossaryTerms(text, lang)       │              │
│    │   │   → List[GlossaryTerm]  (typed output)    │              │
│    │   └──────────────────────────────────────────┘              │
│    │                                                             │
│    └─ RAG retrieval: rag_service.py → Hindsight                 │
│        (no BAML — vector search, not LLM generation)             │
│                                                                  │
│  NEVER: from experiments.adalflow import *                       │
│  NEVER: adalflow in production requirements                      │
└─────────────────────────────────────────────────────────────────┘
```

**Key rule:** AdalFlow discovers prompts; BAML executes them. The boundary is enforced by physical separation — `experiments/adalflow/` is not on `sys.path` in production, and `adalflow` is not in `backend/pyproject.toml`.

---

## Implementation

### Files

| File | Purpose |
|------|---------|
| `backend/baml_src/glossary.baml` | BAML function: `ExtractGlossaryTerms(text, source_lang) → GlossaryTerm[]` with prompt + `{{ ctx.output_format }}` injection |
| `backend/baml_src/clients.baml` | Named client `CFGateway` — `provider "openai"`, CF AI Gateway `/compat` endpoint via env vars |
| `backend/baml_client/` (14 files) | Compiler-generated Python client — Pydantic types, sync/async clients, runtime, tracing, type builders |
| `backend/app/services/glossary_service.py` | Business logic wrapper — input validation, lazy BAML client init, error handling, 8000-char truncation |
| `backend/app/integrations/baml_setup.py` | Env var injection — sets `BAML_GLOSSARY_BASE_URL`, `BAML_GLOSSARY_API_KEY`, `BAML_GLOSSARY_MODEL` before `baml_client` import |
| `backend/pyproject.toml` | `baml-py>=0.222.0` in `[dependency-groups].rag` |
| `experiments/adalflow/rag_recall_opt.py` | AdalFlow Text-Grad prompt optimization — offline only, 791 lines, 20-query eval set |
| `experiments/adalflow/requirements.txt` | `adalflow>=0.2.0`, `openai>=1.0.0` — isolated from backend |
| `experiments/adalflow/optimized_prompt.json` | Saved optimized RAG synthesis prompt (baseline: recall=1.0, delta=0.0) |

### Dependency

```toml
# backend/pyproject.toml — [dependency-groups].rag
rag = [
    "baml-py>=0.222.0",
]
```

BAML lives in the `rag` dependency group because glossary extraction improves cross-language RAG recall (consistent terminology across EN/DE/FR). It is NOT in the `core` group — services that don't need BAML don't pay its import cost.

### Named Client: CFGateway

```baml
# backend/baml_src/clients.baml
client<llm> CFGateway {
  provider "openai"
  options {
    model env.BAML_GLOSSARY_MODEL
    api_key env.BAML_GLOSSARY_API_KEY
    base_url env.BAML_GLOSSARY_BASE_URL
    temperature 0.1
  }
}
```

The `openai` provider type works because CF AI Gateway proxies OpenAI-compatible APIs. The actual values are injected by `backend/app/integrations/baml_setup.py`:

```python
# backend/app/integrations/baml_setup.py (abridged)
def configure() -> None:
    if "BAML_GLOSSARY_BASE_URL" not in os.environ:
        gateway_url = (
            f"https://gateway.ai.cloudflare.com/v1/"
            f"{account_id}/{gateway_id}/compat"
        )
        os.environ["BAML_GLOSSARY_BASE_URL"] = gateway_url
    if "BAML_GLOSSARY_API_KEY" not in os.environ:
        os.environ["BAML_GLOSSARY_API_KEY"] = settings.CLOUDFLARE_API_TOKEN
    if "BAML_GLOSSARY_MODEL" not in os.environ:
        os.environ["BAML_GLOSSARY_MODEL"] = "workers-ai/@cf/meta/llama-4-scout-17b-16e-instruct"
```

### Glossary Function Signature

```baml
# backend/baml_src/glossary.baml (abridged)
class GlossaryTerm {
  term_en string       // Canonical English term
  term_de string       // Canonical German term
  term_fr string       // Canonical French term
  definition string    // Plain-language legal definition (English)
}

function ExtractGlossaryTerms(text: string, source_lang: string) -> GlossaryTerm[] {
  client CFGateway
  prompt #"
    ...extraction rules...
    Source language: {{ source_lang }}
    {{ ctx.output_format }}
    Text:
    ---
    {{ text }}
    ---
  "#
}
```

### Service Layer

```python
# backend/app/services/glossary_service.py (abridged)
def extract_terms(text: str, source_lang: str) -> list[GlossaryTerm]:
    """Extract domain-specific legal terminology from a document text chunk."""
    source_lang = source_lang.lower().strip()
    if source_lang not in ("en", "de", "fr"):
        raise ValueError(f"Unsupported language '{source_lang}'")

    truncated = text[:8000] if len(text) > 8000 else text
    if not truncated.strip():
        return []

    b = _get_baml_client()  # lazy-loads after baml_setup.configure()
    terms = b.ExtractGlossaryTerms(truncated, source_lang)
    return list(terms) if terms else []
```

---

## Alternatives Considered

| Option | Verdict | Notes |
|--------|---------|-------|
| **Manual JSON prompt + `json.loads()`** | ❌ Rejected | No schema enforcement; silent parse failures; same term can return differently across calls |
| **Instructor + Pydantic** | 🟡 Viable | Stronger than manual JSON, but couples to OpenAI client. BAML's compiler-generated types + named clients are more portable across providers. |
| **LangChain `with_structured_output()`** | ❌ Rejected | Heavy dependency for one call pattern; LangChain's abstraction overhead is disproportionate |
| **BAML for ALL four calls** | ❌ Rejected | OCR/translation/retrieval are not prompt→typed-output calls. Forcing BAML onto them adds indirection with zero benefit |
| **AdalFlow in production as the runtime interface** | ❌ Rejected | AdalFlow is an optimization framework (Trainer.fit(), Text-Grad backprop), not a typed-interface compiler. It generates unstructured text, not validated Pydantic models |
| **BAML (runtime) + AdalFlow (offline)** | ✅ **Chosen** | Clean separation: AdalFlow discovers better prompts → developer copies into BAML → BAML executes with type safety at runtime |

---

## Consequences

### Positive
- **Type safety at the boundary:** `b.ExtractGlossaryTerms()` returns `List[GlossaryTerm]`, not `dict` or `str`. BAML's compiler guarantees schema conformance — if the LLM returns malformed JSON, BAML retries with guided repair before the caller sees an error.
- **Prompt/code separation:** The glossary prompt lives in `backend/baml_src/glossary.baml` — readable, version-controlled, and reviewable independently of the Python code that calls it.
- **Provider portability:** Switching from Llama-4-Scout to a different model is a one-line env var change (`BAML_GLOSSARY_MODEL`) — no code change.
- **REM-8 enforced by architecture:** The `CFGateway` named client makes direct provider URLs impossible. Any new BAML client automatically routes through the Gateway.
- **AdalFlow as an optimization force-multiplier:** Offline Text-Grad can improve prompts without touching production code. The experiment already exists at `experiments/adalflow/rag_recall_opt.py`.

### Negative / Risks
- **New DSL to learn:** BAML is a domain-specific language with its own syntax (`.baml` files, generator config, named clients). The team must learn it for any future prompt→typed-output call.
- **Generated code in repo:** `backend/baml_client/` (14 files) is compiler output — must be regenerated when `.baml` files change. CI should enforce `baml-cli generate --check`.
- **Single call today:** BAML is justified for exactly one call pattern. If no second prompt→typed-output call materializes in Sprint 3, BAML remains a heavyweight dependency for one function. **Mitigation:** the RAG answer-synthesis step (future Sprint 3) is a natural second call — prompt + context → typed `SearchResult` with citations.

### Neutral
- `baml-py>=0.222.0` is in the `rag` dependency group — services that don't import `glossary_service.py` don't pay the import cost.
- AdalFlow is fully isolated in `experiments/adalflow/` with its own `requirements.txt`. Zero impact on production dependencies or CI.

---

## Related

- [ADR-005](ADR-005-glossary-terminology.md) — Domain glossary (the call that drives BAML adoption)
- [ADR-007](ADR-007-memory-rag-layer.md) — Single-vendor discipline (same principle applied to LLM generation interface)
- `backend/baml_src/glossary.baml` — ExtractGlossaryTerms function definition
- `backend/baml_src/clients.baml` — CFGateway named client (CF AI Gateway routing)
- `backend/app/services/glossary_service.py` — Business logic wrapper (89 lines)
- `backend/app/integrations/baml_setup.py` — Env var injection for BAML client init (64 lines)
- `backend/baml_client/` — Generated Python client (14 files)
- `backend/pyproject.toml` — `baml-py>=0.222.0` in `[dependency-groups].rag`
- `experiments/adalflow/rag_recall_opt.py` — AdalFlow Text-Grad prompt optimization (791 lines, offline only)
- `experiments/adalflow/optimized_prompt.json` — Saved optimized RAG synthesis prompt
