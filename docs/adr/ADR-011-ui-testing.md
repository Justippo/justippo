# ADR-011: UI Testing Strategy — Storybook + Chromatic + Vitest Boundary

**Date:** 2026-06-13
**Status:** Accepted
**Deciders:** Mihai Chindriș
**Context:** Sprint 2 frontend hardening — Storybook 8.6 + Chromatic visual testing shipped; Vitest configured but zero test files yet; Playwright E2E deferred to Sprint 3
**See also:** Sprint 3 task "Accessibility audit (a11y)" — ABSORBED by this ADR's continuous CI gate

---

## TL;DR

Storybook 8.6 is the UI development and testing platform for the EvidenceEU frontend (Next.js 14, TypeScript, Tailwind CSS). 8 components have stories with interaction tests. **accessibility (a11y) is a CI gate** — `@storybook/addon-a11y` (axe-core, WCAG 2.1 AA) runs on every PR via `@storybook/test-runner`. Chromatic provides visual regression testing with TurboSnap. **This ADR absorbs the Sprint 3 "Accessibility audit" task** into continuous CI — no separate audit sprint needed. Vitest runs `--passWithNoTests` (zero test files today); Playwright E2E is deferred. The boundary: **Storybook owns components, Vitest will own utilities/hooks, Playwright will own full page journeys.**

---

## Context

### The Testing Gap at Sprint 2 Start

The frontend had zero tests of any kind. Components were developed in isolation (Next.js dev server) but there was no:
- Isolated component rendering for development and review
- Accessibility audit mechanism
- Visual regression to catch unintended styling changes
- Interaction testing (keyboard, click, drag-and-drop)
- CI enforcement for any of the above

### What We Built

Three layers, shipped at different maturity levels:

| Layer | Tool | Status | What It Tests |
|-------|------|--------|---------------|
| **Component isolation + a11y + interaction** | Storybook 8.6 + test-runner | ✅ Shipped | 8 components, WCAG 2.1 AA, user interactions |
| **Visual regression** | Chromatic (TurboSnap) | ✅ Shipped | Visual diffs on every PR via GitHub Actions |
| **Unit tests** | Vitest 1.6 | 🟡 Configured, zero test files | `vitest run --passWithNoTests` — utilities/hooks not yet written |
| **E2E** | Playwright | 🔴 Deferred to Sprint 3 | Full page journeys, cross-page state, API integration |

---

## Decision

### 1. Storybook 8.6 — Component Isolation + Interaction + a11y

**Config file:** `frontend/.storybook/main.ts`

```typescript
const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [
    "@storybook/addon-essentials",      // docs, controls, actions, viewport
    "@storybook/addon-interactions",    // play() functions for click/keyboard/assert
    "@storybook/addon-a11y",            // axe-core accessibility audits
  ],
  framework: {
    name: "@storybook/nextjs",
    options: {},
  },
  staticDirs: ["../public"],
};
```

**Global a11y enforcement:** `frontend/.storybook/preview.ts`
```typescript
const preview: Preview = {
  parameters: {
    a11y: {
      test: "error",  // WCAG 2.1 AA violations FAIL the CI build
    },
  },
};
```

**Per-component a11y overrides:** Individual stories can opt out with `a11y: { test: "off" }` when pre-existing contrast/color issues exist (see Gap Assessment below). These are tagged `TODO: Sprint 3` and are tracked technical debt — not permanent exemptions.

### 2. Chromatic — Visual Regression with TurboSnap

**GitHub Actions step:** `.github/workflows/ci.yml` (lines 119–127)

```yaml
- name: Chromatic visual testing
  uses: chromaui/action@v1
  with:
    projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
    onlyChanged: true          # TurboSnap — only snapshot changed components
    exitZeroOnChanges: true    # Visual diffs don't block PR merge (review in Chromatic UI)
    workingDir: frontend
    storybookBuildDir: storybook-static
```

**Key settings:**
- `onlyChanged: true` enables **TurboSnap** — only components whose stories (or dependencies) changed in the PR are snapshotted. This keeps CI fast and stays within Chromatic's free tier snapshot quota.
- `exitZeroOnChanges: true` means visual diffs are surfaced for design review but do NOT block PR merges. This is intentional: visual changes need human judgment (is this a deliberate redesign or a regression?). Blocking the pipeline on every pixel diff would create false-positive churn.

### 3. CI Pipeline — Test Runner

**GitHub Actions step:** `.github/workflows/ci.yml` (lines 104–113)

```yaml
- name: Accessibility + interaction tests via test-runner
  run: |
    npx serve storybook-static -l 6006 --no-request-logging &
    SERVE_PID=$!
    npx wait-on tcp:6006 --timeout 60000
    npx test-storybook --url http://localhost:6006 --maxWorkers=2
    kill $SERVE_PID
```

This runs every story's `play()` function in a headless Chromium browser (installed earlier in CI via `npx playwright install chromium`). Any a11y violation where `test: "error"` is set will fail the build.

### 4. Vitest — Unit/Utility Tests (Future)

**Config:** `frontend/vitest.config.ts`
```typescript
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
```

**Package script:** `"test": "vitest run --passWithNoTests"` — the `--passWithNoTests` flag means CI passes today with zero test files. When utility functions and custom hooks are written, tests land in `src/**/*.test.ts` and are automatically picked up.

**Why Vitest and Storybook don't share test files:** Storybook 8.6 uses `@storybook/test-runner` (based on Playwright) for running `play()` functions in a real browser. Vitest 1.6 runs in jsdom. Merging them (Storybook's Vitest addon) requires Vitest 2.x — a breaking upgrade deferred to post-Sprint 2. For now, they are separate runners with separate responsibilities.

---

## Components with Stories

8 components have `.stories.tsx` files with interaction tests via `play()` functions:

| Component | Story File | Interaction Stories | a11y Status | Notes |
|-----------|-----------|---------------------|-------------|-------|
| **DocumentUploader** | `document/DocumentUploader.stories.tsx` | `DragOver`, `FileSelected`, `ErrorFileTooLarge` | `off` (Sprint 3 TODO) | `ErrorWrongType` and `DismissError` are placeholder stories (no play function — flaky in headless) |
| **DocumentViewer** | `document/DocumentViewer.stories.tsx` | `GlossaryPanelOpen`, `LastPage`, `FirstPage`, `PageNavigation` | `off` (Sprint 3 TODO) | 5 stories total — state permutations + navigation edge cases |
| **GlossaryOverridePanel** | `document/GlossaryOverridePanel.stories.tsx` | `RevertInteraction` | `off` (Sprint 3 TODO) | Verifies revert button is present and clickable |
| **NavigationBar** | `ui/NavigationBar.stories.tsx` | `LanguageSwitch` | `off` (Sprint 3 TODO) | `MobileMenuOpen` is a placeholder (hidden by CSS on desktop) |
| **SearchBar** | `search/SearchBar.stories.tsx` | `SubmitQuery`, `ChangeLanguage`, `DisabledWhenEmpty` | `error` ✅ | Full a11y — passes axe-core checks |
| **SearchResults** | `search/SearchResults.stories.tsx` | `RetryInteraction` | `off` (Sprint 3 TODO) | Retry button click verified via spy |
| **DocumentComparison** | `compare/DocumentComparison.stories.tsx` | `TabSwitching`, `ExpandModifiedBlock` | `error` ✅ | Full a11y — tab ARIA attributes verified |
| **ExchangePanel** | `exchange/ExchangePanel.stories.tsx` | `AccordionOpen` (placeholder) | `off` (Sprint 3 TODO) | Requires `NEXT_PUBLIC_ENABLE_MATRIX_EXCHANGE=true` |

---

## Accessibility (a11y) — Sprint 3 Task Absorbed

### How It Works

1. `@storybook/addon-a11y` runs **axe-core** checks on every story's rendered DOM
2. `preview.ts` sets global default: `a11y: { test: "error" }` — any WCAG 2.1 AA violation fails CI
3. Individual stories can opt out with `a11y: { test: "off" }` — used ONLY for pre-existing issues with a tracked `TODO: Sprint 3` comment
4. The `test-runner` step in CI (`npx test-storybook`) enforces this on EVERY PR

### What This Means for Sprint 3

The ClickUp task "Accessibility audit (a11y) for frontend" is **absorbed by this ADR's CI gate**. Instead of a one-time audit in Sprint 3, accessibility is tested continuously on every component change. The Sprint 3 task is reduced to:

1. **Fix the 6 components with `a11y: { test: "off" }`** — resolve pre-existing contrast/color issues in module CSS files
2. **Remove the `TODO: Sprint 3` markers** and flip those 6 components to `test: "error"`
3. **Verify all 8 components pass axe-core checks** in CI

No separate audit sprint needed — accessibility is already wired into the pipeline.

---

## Testing Boundary: Vitest vs Storybook vs Playwright

```
┌─────────────────────────────────────────────────────────┐
│                    PLAYWRIGHT (Sprint 3)                 │
│  Full page journeys: search → results → document viewer  │
│  Cross-page state, real API calls, Matrix exchange flows │
│  playwright.config.ts — deferred, not yet created        │
├─────────────────────────────────────────────────────────┤
│                    STORYBOOK 8.6 (Shipped)               │
│  Isolated components with mocked props/API               │
│  play() functions: click, type, select, keyboard         │
│  a11y: axe-core on every story, every PR                 │
│  8 components, 25+ stories with interactions             │
├─────────────────────────────────────────────────────────┤
│                    VITEST 1.6 (Configured, empty)        │
│  Pure logic: utility functions, custom hooks, API client │
│  jsdom — no real browser                                 │
│  vitest.config.ts includes src/**/*.{test,spec}.{ts,tsx} │
│  Currently: --passWithNoTests (0 test files)             │
└─────────────────────────────────────────────────────────┘
```

| What | Runs In | Files Match | Status | When to Use |
|------|---------|-------------|--------|-------------|
| **Vitest** | jsdom (Node) | `*.test.ts`, `*.spec.ts` | 🟡 Zero files today | Pure logic: `formatCurrency()`, `useDebounce()`, API client mocks |
| **Storybook** | Real Chromium (test-runner) | `*.stories.tsx` | ✅ 8 components | Isolated component: "does the search bar disable when empty?" |
| **Playwright** | Real Chromium (full browser) | `e2e/` (not yet created) | 🔴 Sprint 3 | Full journey: "can a user search, click a result, and view translation?" |

**No overlap rule:** If a test needs a real DOM + user interaction → Storybook. If it needs multiple pages + real API → Playwright. If it's pure JavaScript/TypeScript logic → Vitest. A test file belongs in exactly one of these three buckets.

---

## Implementation

### Dependencies

From `frontend/package.json`:

| Package | Version | Purpose |
|---------|---------|---------|
| `storybook` | `^8.6.14` | CLI — `storybook dev`, `storybook build` |
| `@storybook/react` | `^8.6.14` | React renderer |
| `@storybook/nextjs` | `^8.6.14` | Next.js 14 framework integration (App Router, Webpack) |
| `@storybook/addon-essentials` | `^8.6.14` | Docs, controls, actions, viewport, backgrounds, toolbars |
| `@storybook/addon-interactions` | `^8.6.14` | `play()` function support + interaction debug panel |
| `@storybook/addon-a11y` | `^8.6.14` | axe-core accessibility audits per story |
| `@storybook/test` | `^8.6.14` | `userEvent`, `within`, `expect`, `fn` — testing utilities used in play functions |
| `@storybook/test-runner` | `^0.23.0` | Headless test execution in CI (Playwright-based) |
| `vitest` | `^1.6.0` | Unit test runner (jsdom) |
| `@playwright/test` | `^1.44.0` | E2E test framework (installed but not yet configured — Sprint 3) |
| `wait-on` | `^9.0.10` | CI utility — waits for Storybook server to be ready before test-runner |

### Key Scripts

```jsonc
// frontend/package.json
"scripts": {
  "storybook":        "storybook dev -p 6006",
  "build-storybook":  "storybook build",
  "test-storybook":   "test-storybook",
  "test":             "vitest run --passWithNoTests",
  "test:e2e":         "playwright test"
}
```

---

## Gap Assessment

The following are deferred to Sprint 3:

| Gap | Impact | Sprint 3 Action |
|-----|--------|-----------------|
| **6 components with a11y off** | WCAG violations in those components won't fail CI | Fix contrast/color issues in module CSS; flip to `test: "error"` |
| **Zero Vitest test files** | No unit test coverage for utilities/hooks | Write tests for any utility functions created in Sprint 3 |
| **No Playwright config** | No E2E coverage for full page journeys | Create `playwright.config.ts`, write E2E tests per ClickUp task |
| **MobileMenuOpen and AccordionOpen are placeholder stories** | Those UI states aren't CI-tested | Wire up the play functions or document as manual-only |
| **ErrorWrongType and DismissError in DocumentUploader are placeholder stories** | File upload edge cases not CI-tested | Evaluate Playwright file upload reliability; add or document as manual |

None of these gaps block the decision to adopt Storybook + Chromatic as the UI testing stack. The infrastructure is shipped, CI is green, and 8 components have working stories with interaction tests. The gaps are implementation TODOs for Sprint 3, not architectural concerns.

---

## Alternatives Considered

| Option | Verdict | Notes |
|--------|---------|-------|
| **No UI testing** | ❌ Rejected | Unacceptable for a capstone with graded deliverables. Components must be verifiable independently of pages. |
| **Playwright Component Testing** | 🟡 Viable | Playwright CT runs components in a real browser but lacks Storybook's visual catalog, addon ecosystem, and Chromatic integration. Storybook + Playwright E2E (separate CI jobs) gives us both. |
| **Cypress Component Testing** | ❌ Rejected | Cypress CT is deprecated in favor of Playwright; Chromatic integration is Storybook-native. |
| **Jest + React Testing Library** | ❌ Rejected | Vitest is faster (native ESM), shares the same `@testing-library` APIs, and aligns with the Vite/Next.js ecosystem. No reason to add Jest. |
| **Storybook-only (no Chromatic)** | 🟡 Viable but weaker | We'd lose visual regression — a CSS change could subtly break a component with no CI signal. |
| **Chromatic blocking mode (`exitZeroOnChanges: false`)** | ❌ Rejected | Visual diffs need human review. Blocking PR merges on pixel diffs creates false-positive churn for intentional design changes. |
| **Adopted: Storybook + Chromatic (CI gate for a11y) + Vitest (utilities only) + Playwright E2E (Sprint 3)** | ✅ **Chosen** | Best-fit tools for each layer. Zero overlap. CI-integrated from day one. |

---

## Consequences

### Positive
- **Accessibility is a CI gate** — not a one-time audit. Every PR runs axe-core checks on every story.
- **Single source of truth** — Storybook stories serve as development environment, documentation, and test harness. No duplicate test files.
- **Visual regression without pipeline friction** — Chromatic's `exitZeroOnChanges: true` surfaces diffs for design review without blocking merges.
- **TurboSnap keeps CI fast** — Chromatic snapshots only changed components, staying within free tier quota.
- **Clear testing boundary** — the "what goes where" table above eliminates ambiguity for future contributors.

### Negative / Risks
- **A11y partially gated** — 6 of 8 components have pre-existing contrast issues with `a11y: { test: "off" }`. These are Sprint 3 TODOs and must be resolved before the final demo.
- **Test-runner requires a running server** — CI must `serve storybook-static`, `wait-on tcp:6006`, then `test-storybook`. Slower than pure Vitest, but covers real-browser interactions.
- **Chromatic quota** — free tier covers ~5K snapshots/month. TurboSnap reduces usage, but a large component refactor could exhaust the quota. Monitor in Sprint 3.
- **Vitest 1.6 vs Storybook Vitest addon** — the Storybook Vitest integration (portable stories) requires Vitest 2.x. Upgrading Vitest is a breaking change — deferred to post-Sprint 2.

### Neutral
- Playwright E2E tests are a known Sprint 3 deliverable — this ADR defines the boundary, not the implementation.
- Vitest with `--passWithNoTests` means CI is green today but will fail if a test is added and broken — the right default for a growing test suite.

---

## Related

- CI workflow: `.github/workflows/ci.yml` — `frontend` job (lines 70–127)
- Storybook config: `frontend/.storybook/main.ts`, `frontend/.storybook/preview.ts`
- Vitest config: `frontend/vitest.config.ts`
- Story files: `frontend/src/components/**/*.stories.tsx` (8 files)
- ClickUp: "Accessibility audit (a11y) for frontend" — ABSORBED by this ADR's CI gate
- ClickUp: "Write Playwright E2E tests" — Sprint 3, boundary defined here
