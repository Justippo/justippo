# Contributing to EvidenceEU

Thank you for your interest in contributing to EvidenceEU!

## Issue First Policy

All PRs must reference an existing issue. Before opening a PR, open an issue describing the bug or feature. This helps the team triage and prevents duplicate work.

- Use `Fixes #123` or `Closes #123` in your PR description to link the issue
- For small fixes, a brief issue is fine — just enough context to understand the problem
- PRs without a linked issue may be closed without review

## Pull Request Expectations

- Keep pull requests small and focused
- Explain the issue and why your change fixes it
- Before adding new functionality, ensure it doesn't already exist elsewhere in the codebase
- If your PR includes UI changes, include screenshots or videos showing before/after

### PR Titles

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: new feature
fix: bug fix
docs: documentation changes
chore: maintenance, dependency updates
refactor: code refactoring without behavior change
test: adding or updating tests
```

Optionally include a scope for package-specific changes:

```
feat(frontend): add dark mode toggle
fix(backend): resolve OCR timeout
chore(worker): bump wrangler version
```

## Developer Certificate of Origin (DCO)

All contributions require a DCO sign-off. By signing off, you certify that
you have the right to submit the contribution under the project's license.

Add a `Signed-off-by` line to your commit messages:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s` to add the sign-off automatically.

## License

- **Backend & Worker:** AGPL-3.0-or-later (see root `LICENSE`)
- **Frontend:** MIT (see `frontend/LICENSE`)
- **Documentation:** CC-BY-4.0 (see `LICENSES/CC-BY-4.0.txt`)

By contributing, you agree that your contributions will be licensed under
the same license as the component you are modifying.

## Getting Started

```bash
make dev          # Full stack via Docker Compose
make lint         # Ruff (backend) + ESLint (frontend)
make format       # Ruff + Prettier
make test-backend # pytest
make test-frontend # Vitest
make test-e2e     # Playwright
```

See the root `AGENTS.md` for architecture details, constraints, and gotchas.

## Style Preferences

These are not strictly enforced by linters — they are guidelines for writing readable code:

- **Functions:** Keep logic within a single function unless breaking it out adds clear reuse or composition benefits
- **Control flow:** Prefer early returns over nested conditionals
- **Error handling:** Prefer specific error types over generic catch-alls
- **Types:** Reach for precise types; avoid `any`
- **Variables:** Prefer immutable patterns (`const` over `let`)
- **Naming:** Choose concise single-word identifiers when they remain descriptive
- **DRY:** If you copy-paste more than 3 lines, extract a helper
