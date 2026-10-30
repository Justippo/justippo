# ADR-013: Release Tagging Strategy

**Date:** 2026-06-26
**Status:** Accepted
**Decision Maker:** Mihai Chindriș (PO/Dev)

## Context

EvidenceEU had no formal release tagging strategy. The only tags were SRS document versions (`v1.3-srs`, `v1.4-srs`) — and those were missing v1.0 through v1.2. With 407 commits across 3 sprints and the capstone deadline approaching, we need a structured approach to mark sprint boundaries and communicate changes.

Research: [OpenCode (AnomalyCo)](https://github.com/anomalyco/opencode/releases) uses semantic versioning with categorized GitHub releases. [SemVer 2.0.0](https://semver.org/) recommends pre-1.0 versions (`0.x.y`) for initial development. [CloudBees](https://www.cloudbees.com/blog/best-practices-when-versioning-a-release) recommends starting at 0.1.0 and incrementing minor per release. [GeekLaunch](https://geeklaunch.io/blog/versioning/) recommends releasing 1.0.0 sooner rather than later for small projects reaching MVP.

## Decision

### Two Tag Types (Coexisting)

| Tag Type | Format | Purpose | Example |
|----------|--------|---------|---------|
| **Software release** | `v{MAJOR}.{MINOR}.{PATCH}` | Marks sprint/delivery milestones — the actual deployed software | `v0.1.0`, `v0.2.0` |
| **SRS document** | `v{MAJOR}.{MINOR}-srs` | Marks SRS document revisions — independent of software releases | `v1.4-srs` |

### Software Versioning (Pre-1.0 → 1.0 at Capstone Submission)

EvidenceEU uses **pre-1.0 semantic versioning** during development:

- **`v0.x.0`** — Sprint releases (MINOR bump per sprint)
- **`v0.x.y`** — Hotfix/patch releases within a sprint (PATCH bump)
- **`v1.0.0`** — First production-ready release (capstone submission)

**When do we hit v1.0.0?** The capstone submission marks the first time the product is feature-complete, deployed to production, demoed end-to-end, and documented. The three core pillars (search, translation, exchange) are all working. Staying at 0.x forever signals "not ready" — v1.0.0 communicates that the product is usable. Post-capstone, v1.x.y would be feature updates and v2.0.0 would be a major platform shift (e.g., adding healthcare/EHDS from Phase 2 scope).

### Sprint → Release Mapping

| Tag | Sprint | Date Range | Description | Status |
|-----|--------|------------|-------------|--------|
| `v0.1.0` | Sprint 1 | May 14 – May 30 | Infra & RAG foundation | ✅ Complete |
| `v0.2.0` | Sprint 2 | Jun 2 – Jun 29 | Translation & UI | ⚠️ In progress (5 issues remaining for Sprint 2) |
| `v0.3.0` | Sprint 3 | Jun 29 – Jul 22 | Matrix, Polish & Demo | ✅ Complete |
| `v1.0.0` | Capstone | — | First production-ready release | ✅ Released (v1.0.0) |

### Incomplete Sprint Releases

When a sprint tag is created before all sprint tasks are complete, the GitHub Release notes include a prominent notice:

```markdown
> ⚠️ **Sprint X In Progress** — N issues remain open (#X, #Y, #Z). These will be completed within Sprint X.
> This tag marks the codebase boundary at this point in time, not full sprint completion.
```

This preserves an accurate timeline — the tag marks *what was deployed at that point in time*, not what was planned. The tag may be moved to a later commit if the sprint end date changes.

### Sprint 3 Tag Timing

**The `v0.3.0` tag should be created at Sprint 3 completion, not now.** Creating it prematurely would:
1. Tag code that hasn't been written yet (Sprint 3 just started)
2. Misrepresent the state of the codebase
3. Violate the "tag = deployed milestone" principle

The `v0.3.0` tag will be created when Sprint 3 closes — either at the capstone submission or when the team declares Sprint 3 done. If `v0.3.0` and `v1.0.0` coincide (Sprint 3 completion = capstone submission), both tags point to the same commit.

### SRS Document Tags (Independent Timeline)

SRS tags track document revisions, not software releases. They have their own version sequence starting at v1.0:

| Tag | Date | Description |
|-----|------|-------------|
| `v1.0-srs` | May 27 | Initial scaffold |
| `v1.1-srs` | Jun 19 | Backend slice review (FR notes, NFR evidence, Pyodide constraints) |
| `v1.2-srs` | Jun 19 | FR-03 layout correction, ISO 25010:2023 NFR column |
| `v1.3-srs` | Jun 19 | FR-05/06/10/11/12/14 notes, Section 6 expanded |
| `v1.4-srs` | Jun 26 | Final team review (translation criteria, NFR-T1/T2, QA harness) |

> **Why SRS starts at v1.0 while software starts at v0.1:** The SRS was a complete document from the first commit — it had all 14 FRs and 10 NFRs scaffolded. It was "v1.0-worthy" as a draft. The software, by contrast, started as a scaffold with no working features. SRS v1.0 = "first complete draft." Software v0.1.0 = "first sprint, incomplete product."

### GitHub Releases

Each software tag gets a GitHub Release with categorized notes (OpenCode pattern):

```markdown
## Core
### Features
- ...
### Bug Fixes
- ...

## Frontend
### Features
- ...
```

### Conventional Commits

The project uses conventional commit prefixes (`feat`, `fix`, `chore`, `docs`, `ci`, `refactor`, `test`, `style`, `perf`, `build`). These map to release note categories:
- `feat` → Features
- `fix` → Bug Fixes
- `docs` → Documentation
- `chore`/`ci` → Infrastructure
- `refactor`/`test`/`style`/`perf` → Improvements

### Tag Creation Process

```bash
# Sprint release (at sprint end)
git tag -a v0.3.0 -m "Sprint 3 — Matrix, Polish & Demo"
git push origin v0.3.0

# Create GitHub release with notes
gh release create v0.3.0 --title "v0.3.0 — Sprint 3" --notes-file release-notes.md

# SRS document tag (independent of software releases)
git tag -a v1.5-srs -m "SRS v1.5 — ..."
git push origin v1.5-srs
```

### Why Not Automated Release Tooling?

For a 4-person capstone with 3 sprints, manual tagging is simpler and more reliable than setting up release-please, semantic-release, or changesets. The overhead of automation tooling + CI integration isn't justified for ≤5 total releases.

## Consequences

- Retroactive tags created for Sprint 1 (`v0.1.0`) and Sprint 2 (`v0.2.0`)
- Retroactive SRS tags created for v1.0 through v1.2 (were missing)
- GitHub Releases created with generated changelogs from conventional commits
- SRS tags (`v*-srs`) continue independently — no collision with semver tags
- `v0.3.0` created at Sprint 3 completion; `v1.0.0` at capstone submission
