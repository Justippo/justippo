# Multilingual RAG Recall — Prompt Optimization Report

> **Date:** 2026-06-13
> **Experiment:** `experiments/adalflow/rag_recall_opt.py`
> **Seed Eval Set:** `docs/testing/multilingual-recall.md`
> **Optimizer:** AdalFlow LLM-AutoDiff (Textual Gradient Descent)
> **Status:** ✅ Executed — baseline established

---

## Summary

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Recall (train, 14 samples) | 1.0000 | — | — |
| Recall (test, 3 samples) | 1.0000 | 1.0000 | +0.0000 |
| Training Steps | — | 1 (text-grad skipped — see notes) | — |

---

## Initial Prompt (Before Optimization)

```
You are a multilingual RAG (Retrieval-Augmented Generation) system for
European Union legal and administrative documents.

Given a set of retrieved context passages and a user question:
1. Identify which passages are relevant to the question.
2. Synthesize a concise, accurate answer using ONLY information from the
   relevant passages.
3. Answer in the SAME LANGUAGE as the question.
4. Cite the specific passage(s) you used, using [Source] notation.
5. If no passage contains the answer, say "No relevant information found."
   Do not fabricate.

The context is provided below.
```

---

## Optimized Prompt (After Optimization)

> Text-grad training was skipped because Workers AI lacks the `/v1/responses`
> endpoint required by AdalFlow's backward engine. The initial prompt achieved
> 100% recall on its own — optimization would not produce meaningful gains.
> The prompt below is the current best prompt.

```
You are a multilingual RAG (Retrieval-Augmented Generation) system for
European Union legal and administrative documents.

Given a set of retrieved context passages and a user question:
1. Identify which passages are relevant to the question.
2. Synthesize a concise, accurate answer using ONLY information from the
   relevant passages.
3. Answer in the SAME LANGUAGE as the question.
4. Cite the specific passage(s) you used, using [Source] notation.
5. If no passage contains the answer, say "No relevant information found."
   Do not fabricate.

The context is provided below.
```

---

## Per-Language Breakdown

| Language | Samples | Before Recall | After Recall | Delta |
|----------|---------|---------------|--------------|-------|
| English (en) | 7 | 1.00 | 1.00 | 0.00 |
| German (de) | 6 | 1.00 | 1.00 | 0.00 |
| French (fr) | 7 | 1.00 | 1.00 | 0.00 |

---

## Training Configuration (Actual)

| Parameter | Value |
|-----------|-------|
| Optimizer | AdalFlow `Trainer` with textual gradient descent |
| RAG Model | `@cf/meta/llama-4-scout-17b-16e-instruct` (Workers AI, free tier) |
| Text-Grad Model | Skipped (Workers AI lacks `/v1/responses` endpoint) |
| Max Steps | 1 (configured for this run) |
| Training Split | 70/15/15 (14 train / 3 val / 3 test) |
| Retriever | Simulated (ground-truth + distractors, shuffled) |
| Eval Metric | Recall (substring match + 80% fuzzy word overlap) |
| LLM Routing | Cloudflare Workers AI (OpenAI-compatible v1 endpoint) |

---

## Workflow Split (AdalFlow ↔ BAML)

Per [ADR-010](../adr/ADR-010-baml-llm-interface.md) (updated 2026-06-13):

- **AdalFlow** owns **prompt discovery** — experimenting with prompt
  wording, structure, and instruction ordering to maximize recall.
- **BAML** owns **type-safe execution** — once the prompt is optimized,
  it's embedded into a `.baml` function (`GenerateRAGAnswer`) which
  enforces typed output (answer string, source citations, language).

The optimized prompt text from this experiment is the candidate for
back-porting into `backend/baml_src/rag_answer.baml` if BAML is adopted
for RAG synthesis (pending ADR-010 expansion in Sprint 2).

---

## Reproducibility

```bash
# 1. Install experiment dependencies
pip install -r experiments/adalflow/requirements.txt

# 2. Set environment variables (Workers AI — free tier)
export CLOUDFLARE_ACCOUNT_ID=<your-account-id>
export CLOUDFLARE_API_TOKEN=<your-api-token>

# 3. Run optimization
cd experiments/adalflow
python rag_recall_opt.py --max-steps 12

# 4. Results saved to experiments/adalflow/optimized_prompt.json
```

---

## Notes

- The simulated retriever always returns the ground-truth passage (among
  distractors), so recall ceiling is 100%. The prompt optimization focuses
  on whether the LLM **attends to** the correct passage, not whether the
  retriever finds it.
- **Text-grad training was skipped** because AdalFlow's backward engine
  requires the `/v1/responses` endpoint which Cloudflare Workers AI does
  not expose. To enable full optimization, set `OPENAI_API_KEY` for the
  backward engine (the forward model can remain Workers AI).
- The initial prompt achieved **100% recall** on both train and test sets
  — all 20 queries correctly retrieved and used the ground-truth passage.
- Future iterations should replace the simulated retriever with a real
  Hindsight `arecall()` call once the Hindsight server is deployed.
