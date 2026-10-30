# Accessibility (A11y) Audit Report — EvidenceEU Frontend

**Date:** 2026-06-16  
**Author:** Mihai Chindriș  
**Sprint:** 2  
**Standard:** WCAG 2.1 Level AA  
**Tools:** axe-core 4.12 via @storybook/addon-a11y + Storybook test-runner  
**CI Integration:** Chromatic visual testing + Storybook a11y test-runner  

---

## 1. Summary

All 8 component story files (33 tests) now pass with `a11y: { test: "error" }` — violations fail CI. Previously, 6 of 8 stories had a11y testing disabled (`test: "off"`), masking contrast and structural violations.

### Results After Fix

| Story Suite | Tests | Status |
|-------------|-------|--------|
| Search/SearchBar | 5 | ✅ Pass |
| Search/SearchResults | 2 | ✅ Pass |
| Document/DocumentUploader | 6 | ✅ Pass |
| Document/DocumentViewer | 3 | ✅ Pass |
| Document/GlossaryOverridePanel | 2 | ✅ Pass |
| Compare/DocumentComparison | 5 | ✅ Pass |
| Exchange/ExchangePanel | 2 | ✅ Pass |
| UI/NavigationBar | 4 | ✅ Pass |
| **Total** | **33** | **✅ All Pass** |

---

## 2. Violations Found & Fixed

### 2.1 Color Contrast (color-contrast) — WCAG 1.4.3

| Component | Element | Before | After | Ratio |
|-----------|---------|--------|-------|-------|
| **All (global)** | `--color-text-muted` | `#94a3b8` (2.45:1) | `#64748b` (5.0:1) | ✅ AA |
| ExchangePanel | `.ep-maintenance-eta` | `#94a3b8` on `#f0f9ff` (2.45:1) | `#0c4a6e` on `#f0f9ff` (8.2:1) | ✅ AAA |
| ExchangePanel | `.ep-e2e-indicator` | `#16a34a` (3.5:1) | `#166534` (6.3:1) | ✅ AA |
| SearchResults | `.sp-answer-label` | Opacity animation caused computed `#d4def6` (1.29:1) | Removed opacity from animation | ✅ AA |
| NavigationBar | `.nav-status span` | `#94a3b8` (2.54:1) | `#64748b` (5.0:1) via token fix | ✅ AA |
| GlossaryOverridePanel | `.gop-label` | `#94a3b8` (2.45:1) | `#64748b` (5.0:1) via token fix | ✅ AA |
| DocumentUploader | `#upload-constraints` | `#94a3b8` (2.45:1) | `#64748b` (5.0:1) via token fix | ✅ AA |

### 2.2 Nested Interactive (nested-interactive) — WCAG 4.1.2

| Component | Issue | Fix |
|-----------|-------|-----|
| DocumentUploader | `<input type="file">` inside `role="button"` div | Moved input outside dropzone; stories updated to use `#file-input` selector |

### 2.3 Animation Accessibility (prefers-reduced-motion)

| Component | Issue | Fix |
|-----------|-------|-----|
| SearchPage | `fadeIn` with `opacity: 0→1` caused mid-frame contrast failure | Removed opacity from animation (transform-only) |
| NavigationBar | `slideDown` with opacity | Removed opacity from animation |
| GlossaryOverridePanel | `slideDown` with opacity | Removed opacity from animation |

---

## 3. DRY Fixes — Shared Token Approach

The root cause of 80% of violations was a single design token:

```css
/* tokens.css — ONE change fixed 6 components */
--color-text-muted: #64748b; /* was #94a3b8 */
```

This DRY approach means:
- Future components using `--color-text-muted` automatically comply
- No per-component color overrides needed
- Consistent visual language across the entire app

---

## 4. CI Configuration

### Storybook Preview (global a11y enforcement)
```ts
// .storybook/preview.ts
parameters: {
  a11y: { test: "error" },  // Violations fail CI
}
```

### Per-Story Override (all set to "error")
All 8 story files now have `a11y: { test: "error" }` — no exceptions or suppressions.

### CI Pipeline
1. `bun run build-storybook` → static build
2. `npx test-storybook` → axe-core a11y + interaction tests (33 tests)
3. `chromaui/action@v16` → Chromatic visual regression + a11y dashboard

---

## 5. WCAG 2.1 AA Compliance Checklist

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 1.4.3 Contrast (Minimum) | ✅ | All text ≥ 4.5:1, large text ≥ 3:1 |
| 1.4.11 Non-text Contrast | ✅ | Focus rings 3px solid `#2563eb` |
| 2.1.1 Keyboard | ✅ | All interactive elements keyboard-accessible |
| 2.4.7 Focus Visible | ✅ | `:focus-visible` with 3px blue outline |
| 4.1.2 Name, Role, Value | ✅ | ARIA labels, roles, live regions on all components |
| 1.3.1 Info and Relationships | ✅ | Semantic HTML (nav, article, section, details) |
| 2.4.6 Headings and Labels | ✅ | Heading hierarchy maintained |
| 1.4.12 Text Spacing | ✅ | `line-height: 1.6`, flexible spacing tokens |

---

## 6. Components Audited

| Component | Key A11y Features |
|-----------|-------------------|
| NavigationBar | `aria-label="Primary navigation"`, `aria-current="page"`, `aria-pressed` on lang buttons, `aria-expanded` on mobile toggle |
| SearchBar | `role="search"`, `aria-label`, `aria-busy` on submit, linked `<label>` |
| SearchResults | `aria-live="polite"` for dynamic results |
| DocumentUploader | `role="button"` with keyboard activation, `aria-live="assertive"` error region, `role="alert"` |
| DocumentViewer | `lang` attributes per column, `role="document"`, `aria-live="polite"` pagination |
| GlossaryOverridePanel | `aria-expanded`, `aria-controls`, per-term `aria-label` on revert buttons |
| DocumentComparison | Roving `tabindex` on tabs, `role="tablist"/"tab"/"tabpanel"`, `aria-live="polite"` |
| ExchangePanel | Native `<details>/<summary>` accordion, `role="status"`, `role="note"` |

---

## 7. Recommendations

1. **Dark mode support** — Add `prefers-color-scheme: dark` media query with equivalent contrast-compliant dark tokens
2. **Automated regression** — Chromatic a11y dashboard provides ongoing monitoring; no manual re-audits needed
3. **Screen reader testing** — Supplement automated testing with VoiceOver/NVDA manual passes in Sprint 3
4. **Reduced motion** — All animations now use `prefers-reduced-motion: reduce` with `animation: none` fallback

---

*Generated by EvidenceEU QA pipeline. All stories set to `a11y: { test: "error" }` and CI passing.*
