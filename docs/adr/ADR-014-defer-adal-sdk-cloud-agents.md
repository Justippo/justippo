# ADR-014: Defer AdaL SDK & Cloud Agents to Post-Capstone

**Date:** 2026-07-03
**Status:** Accepted
**Decision Maker:** Mihai Chindriș (PO/Dev)

## Context

AdaL offers three ways to build with it: (1) the CLI/IDE agent used for development, (2) the **AdaL Agent SDK** — a Python SDK for embedding the agent runtime inside your own application, and (3) **AdaL Cloud Agents** — a hosted, HTTP-callable agent runtime for production agents serving end users.

We evaluated whether the SDK or Cloud Agents are needed for the EvidenceEU capstone (cross-border multilingual document intelligence).

EvidenceEU already has its own backend:
- **FastAPI (Pyodide/Cloudflare Worker)** with its own agent loop for OCR, translation, and glossary extraction.
- **Hindsight RAG** pipeline for search (`backend/app/integrations/`), called via the Cloudflare AI Gateway (CI-enforced, ADR-007).
- **BAML** type-safe LLM extraction (`backend/app/integrations/baml_setup.py`), and a separate **AdalFlow** offline prompt-optimization experiment (`experiments/adalflow/`).

The product's "chat / agent" surface (Chat flow, screens 55–69) is served by this in-house RAG + translation backend, not by an external agent runtime.

Research:
- [AdaL SDK Quick Start](https://docs.sylph.ai/sdk/quick-start) — `query()` / `AdalAgentClient` for embedding the runtime in Python apps.
- [AdaL Cloud Agents Overview](https://docs.sylph.ai/cloud-agents/overview) — hosted agent harness, HTTP API, custom tools/system prompt, no infra to maintain.
- [AdaL Custom Tools](https://docs.sylph.ai/features/custom-tools) and [Custom System Prompt](https://docs.sylph.ai/features/custom-system-prompt) — same building blocks as CLI/SDK.

## Decision

**Do NOT adopt the AdaL Agent SDK or AdaL Cloud Agents for the capstone.** Continue using the AdaL CLI (and opencode) only as the *development* agent. The capstone's agent/runtime needs are fully met by the existing in-house backend.

These capabilities are explicitly deferred to **post-capstone** and would only be reconsidered if scope expands to a user-facing, agent-driven feature that the current backend does not cover — for example:
- A hosted "Ask the documents" assistant exposed to end users without running our own RAG (Cloud Agents candidate).
- Embedding an AdaL-powered agent inside a separate Python service or notebook workflow (SDK candidate).
- A migrant-facing conversational agent that goes beyond the current RAG search (Phase 2 / healthcare-EHDS territory, already out of MVP scope per AGENTS.md).

### What we ARE using now (in-scope tooling)
| Tool | Role | Config |
|------|------|--------|
| AdaL CLI / opencode | Development coding agent | `~/.adal/settings.json` (AdaL) + `opencode.json` (opencode) |
| `stitch-proxy` MCP | Read Stitch design source of truth | `~/.adal/settings.json` |
| `hindsight` MCP | Memory bank (retain/recall/reflect) | `~/.adal/settings.json` |
| `github` MCP | Manage Issues/PRs from the agent | `~/.adal/settings.json` |

## Consequences

- No SDK integration, no Cloud Agent deployment, no extra infra or billing for the capstone.
- The Chat flow (screens 55–69) remains backed by the in-house Hindsight RAG + translation backend (ADR-007), not an external agent runtime.
- If a post-capstone agent-facing feature is scoped, revisit this ADR and select SDK vs Cloud Agents based on whether the agent must run inside our Python backend (SDK) or be exposed to end users over HTTP without us operating runtime infra (Cloud Agents).
- `docs/reference/production-component-guide.md` documents the in-scope MCP/skills; SDK/Cloud are intentionally absent there.
