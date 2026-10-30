# BabelDOC AGPL-3.0 Notice

EvidenceEU uses BabelDOC as an isolated Docker sidecar (`sidecars/babeldoc/`).
The AGPL-3.0 license does NOT propagate to the EvidenceEU core because
communication occurs exclusively over HTTP (see ADR-012).

## Boundary Rules

- EvidenceEU backend communicates with BabelDOC only over HTTP POST.
- BabelDOC dependencies are NOT in `backend/pyproject.toml`.
- Do NOT import `babeldoc` in `backend/app/`, `worker/`, or `frontend/`.
- An AST test in `test_babeldoc_adapter.py` enforces this boundary in CI.

## Distribution

When distributing the community sidecar image (which contains BabelDOC):
- Include this notice and the full AGPL-3.0 text (`LICENSES/AGPL-3.0-or-later.txt`)
- Provide a source-code offer or link to the upstream repo:
  https://github.com/funstory-ai/BabelDOC

## Status

- **ADR-008:** Accepted (2026-06-26) — AGPL Open Core strategy confirmed.
- **GitHub #42:** Resolved — licensing decision finalized.
- **Upstream license:** BabelDOC cannot provide a commercial license (BabelDOC#595).
