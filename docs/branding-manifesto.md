# EvidenceEU Branding Manifesto

> **Single source of truth for platform visual identity.**
> All other UI docs (`docs/reference/production-component-guide.md`,
> `docs/stitch-reference/stitch-generation-prompts.md`) are implementation guides — this file defines
> the *what* and *why* of the brand. Update this file when the brand evolves.

---

## Current version: v1.0 (2026-07-14)

### Brand identity

**EvidenceEU** is a multilingual document intelligence platform for cross-border
users in Europe. Phase 1 (shipped) serves migrants, legal professionals, and HR
with search, translation, and secure exchange; Phase 2 (roadmap) extends the same
engine into healthcare and the European Health Data Space (EHDS) as an
"OpenEvidence for Europe" clinical decision-support layer. The visual brand blends
two qualities:

1. **Institutional trustworthiness** — as credible as a European public
   institution (EU Commission, Court of Justice). Authoritative but not
   bureaucratic.
2. **Modern product polish** — as intentional as a flagship product launch.
   Refined but not sterile.

The design must feel European, not British. It must feel like a startup, not a
government portal. It must not be a copycat of any single reference site.

### Design inspirations (informed, not copied)

| Tier | Sites | What we take |
|------|-------|-------------|
| Tier 1 (primary) | Harvey, Legora | Legal-AI polish, collaborative clarity, restraint |
| Tier 2 (EU/institutional) | europe2031.ai, curia.europa.eu, law.stanford.edu, legali.ai | European institutional gravity, editorial seriousness |
| Tier 3 (legal-AI landscape) | deepjudge.ai, juristic.io, irys.ai, trovato.ai, forseti.is, zh.ch, eduskunta.fi, etc. | Broader legal-tech patterns, EU member state public-sector aesthetics |
| Medtech (Phase 2) | openevidence.com (hard req), sunoh.ai, alphafold.com, abridge.com | Extensibility — design must accommodate healthcare in v2 without rebranding |

**Anti-pattern:** Do not clone any single site. Extract color, typography, and
layout principles; synthesize into a unique EvidenceEU identity.

---

## Color system

### Design token values (v1.0)

All hex values are defined **once** in `frontend/src/styles/tokens.css`.
Components reference via Tailwind theme classes or `var(--*)`. Zero hardcoded
hex in component code (enforced by `scripts/validate.js`).

| Token | Hex | Source / rationale |
|-------|-----|-------------------|
| `--color-primary` | `#005796` | EvidenceEU's own blue — deliberately positioned between EU ECL blue (`#004494`) and GOV.UK brand blue (`#1d70b8`). Not a copy of either. |
| `--color-primary-container` | `#1B5E9E` | Darker EU blue shade. Chosen to pass WCAG 2.1 AA contrast (4.5:1) with light text (`#e9f1ff`). EU ECL Blue 75 (`#4073af`) failed AA — too light. Distinct from both GOV.UK `#1d70b8` and our primary `#005796`. |
| `--color-on-primary` | `#ffffff` | White text on primary. |
| `--color-error` | `#DA2130` | EU ECL error red (`ecl-color-error`). Replaces old GOV.UK `#d4351c`. |
| `--color-warning` | `#8B4A0B` | EU ECL warning orange (`#f29527`) darkened for WCAG AA compliance. Original EU ECL value fails AA as text (2.19:1). Darkened to pass both as text-on-surface (6.48:1) and as background with white text (6.81:1). |
| `--color-success` | `#467A39` | EU ECL success green (`ecl-color-success`). Replaces old GOV.UK `#00703c`. |
| `--color-surface` | `#faf9f8` | Warm off-white background. |
| `--color-on-surface` | `#1a1c1c` | Primary text. |
| `--color-on-surface-variant` | `#414751` | Secondary text. |
| `--color-outline` | `#717782` | Borders. |
| `--color-outline-variant` | `#c1c7d2` | Light borders. |
| `--color-focus` | `#FFD617` | EU ECL yellow (`ecl-color-secondary`). Replaces GOV.UK `#ffdd00`. |

### Why these values (not GOV.UK)

Previous token values (pre-v1.0) were exact copies of the GOV.UK Design System.
6 of 7 tokens matched GOV.UK hex-for-hex, giving the platform an unmistakably
British institutional look. The v1.0 remediation shifts functional colors to EU
ECL (European Commission Component Library) equivalents while keeping
`#005796` as a unique primary that's visually adjacent to EU blue but not
identical to any existing design system.

**Verification sources:**
- EU ECL colors: https://ec.europa.eu/component-library/v3.13.0/ec/guidelines/colours/
- GOV.UK colors: https://design-system.service.gov.uk/styles/colour/

### Legacy alias layer

`tokens.css` also defines `--stitch-*` aliases that map to the canonical
`--color-*` tokens. These exist for backward compatibility with CSS Modules
from the initial implementation. New components should use `--color-*`
directly; the `--stitch-*` layer will be removed in v2.0.

---

## Typography

### Font stack

```
--font-sans: -apple-system, BlinkMacSystemFont, var(--font-inter), "Segoe UI", system-ui, sans-serif
--font-mono: var(--font-jetbrains-mono), "Fira Code", monospace
```

- **Apple devices** render true San Francisco (system font).
- **Non-Apple devices** render **Inter** (closest open-source SF substitute).
- **Code** renders JetBrains Mono.
- Fonts are installed **locally** via `@font-face` / `next/font/local` — no
  Google Fonts CDN imports anywhere in the codebase.

### Type scale

| Token | Size / Line-height | Weight | Use |
|-------|-------------------|--------|-----|
| Headline XL | 36px / 44px | 700 | Page titles, hero |
| Headline LG | 24px / 32px | 700 | Section headers |
| Headline MD | 19px / 28px | 700 | Card titles |
| Body LG | 19px / 28px | 400 | Body text (large) |
| Body MD | 16px / 24px | 400 | Default body |
| Label MD | 16px / 24px | 700 | Buttons |
| Label SM | 14px / 20px | 400 | Captions |
| Code | 14px / 20px | 400 | Code blocks |

---

## Component architecture rules (non-negotiable)

1. **All props: `Readonly<T>` or `ReadonlyArray<T>`** — AST-validated by `scripts/validate.js`.
2. **All logic in `src/hooks/use*.ts`** — components are presentational only.
3. **Tailwind + CSS vars only** — zero hardcoded hex in `.ts/.tsx` files.
4. **Barrel `index.ts`** in every component folder.
5. **Icons: `lucide-react` named imports only**, color via `currentColor`.
6. **Zero emojis** anywhere (including `\u{1F}` unicode escapes).
7. **Every screen in all 4 states:** loading (skeleton, no spinner under 1s), success, error (user-friendly message + next action), empty (helpful CTA).
8. **WCAG 2.1 AA** — contrast, keyboard nav, screen-reader labels, `prefers-reduced-motion`, `prefers-reduced-transparency`.

### Banned copy strings (zero tolerance)

`Connecting to backend` | `Connecting…` | `Demo mode` | `backend offline` |
`Connection lost` | `mock login` | `Sprint 3` | `truncated for demo` |
`github.com` | `Inspect, audit` | `MIT licensed` | `prototype`

---

## Design source of truth

- **Stitch project:** `16375579204261083556` (105 screens, desktop + mobile)
- **Do NOT use** the archived project `14853395309297419919`
- **Screen-to-route mapping:** `docs/stitch-reference/screen-mapping.md`
- **Implementation guide:** `docs/reference/production-component-guide.md`

---

## Version history

### v1.0 (2026-07-14) — EU branding remediation
- Replaced 6 GOV.UK color values with EU ECL equivalents
- Kept `#005796` as unique primary (not a copy of any design system)
- Added this manifesto as single source of truth for brand identity
- Fixed stale "cracked/cool/exciting" vibe language in revamp guide

### Pre-v1.0 (2026-05-26 — 2026-07-13) — the initial implementation
- Landing page with scroll-driven narrative (PR #168)
- 105 Stitch screens mapped to routes
- Tokens were exact GOV.UK copies (the copycat problem)
- All 4 states implemented, WCAG 2.1 AA, 262 Vitest tests passing

---

## v2.0 aspirations (post-capstone)

- Remove `--stitch-*` legacy alias layer (full migration to `--color-*`)
- Consider adopting exact EU blue `#004494` if `#005796` proves too close to GOV.UK in user testing
- Evaluate Public Sans vs Inter for the institutional persona (currently Inter/SF)
- Dark mode design tokens (currently only ad-hoc dark mode in compare screen)
- Motion design language (scroll-driven landing narrative → broader motion system)
- Medtech extensibility check (Phase 2 design must work for healthcare without rebrand)

---

## Implementation docs (reference, not duplication)

| Doc | Scope | When to read |
|-----|-------|-------------|
| `docs/reference/production-component-guide.md` | Atomic Design mechanics, per-flow prompt templates, 105-screen inventory | Building components |
| `docs/stitch-reference/stitch-generation-prompts.md` | Stitch design system specs (colors, type scale, spacing) | Generating new Stitch screens |
| `docs/stitch-reference/screen-mapping.md` | Screen ID → route mapping (105 screens) | Wiring screens to routes |
| `docs/stitch-reference/wireframe-annotations-guide.md` | Wireframe annotation conventions | Designing new flows |
| `frontend/AGENTS.md` | Component org, CSS Modules + Tailwind, Storybook, Vitest conventions | Writing frontend code |
| `AGENTS.md` → "UI Revamp Context (Issue #30)" | Non-negotiable rules, banned strings, tokens table | Every frontend session |