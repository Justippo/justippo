# Frontend Conventions

Next.js / React / TypeScript / Tailwind CSS / Storybook

---

## Key Patterns

- **App Router** — `src/app/` with `page.tsx` and `layout.tsx` files
- **Components** in `src/components/{domain}/` — one directory per domain (document, search, exchange, compare, ui)
- **Barrel `index.ts`** in every new component folder (UI Revamp)
- **Stories co-located** with components — `*.stories.tsx` next to the component file
- **Tests in `__tests__/`** — per-component test directories
- **Types** in `src/types/index.ts`
- **Mocks** in `src/mocks/` — shared between tests and Storybook
- **Props:** `Readonly<T>` or `ReadonlyArray<T>` — no mutable props (UI Revamp)
- **Logic:** all business logic in `src/hooks/use*.ts` files only — components are presentational (UI Revamp)
- **Icons:** `lucide-react` named imports only, color via `currentColor` (UI Revamp)
- **CSS Modules** — `.module.css` files for pre-revamp components; Tailwind + CSS vars for new revamp work

## Component Organization

```
src/components/{domain}/
├── ComponentName.tsx
├── ComponentName.module.css
├── ComponentName.stories.tsx
└── __tests__/
    └── ComponentName.test.tsx
```

## Testing

```bash
bun run test         # Vitest (unit)
npx playwright test  # Playwright (E2E) — npx required, Playwright doesn't support Bun
bun run storybook    # Storybook dev server
```

## Storybook

- Config in `.storybook/main.ts`
- Stories auto-discovered by `../src/**/*.stories.@(ts|tsx)`
- Addons: essentials, interactions, a11y
- Chromatic visual regression runs in CI
- No MDX configured — use pure TSX story files

## CSS Conventions

- **Design tokens** in `src/styles/tokens.css` — CSS custom properties for colors, spacing, typography
- **Globals** in `src/app/globals.css` — reset, base styles
- **UI Revamp (Issue #30):** Tailwind with theme-mapped CSS variables is the standard — zero hardcoded hex in component files. See root `AGENTS.md` → "UI Revamp Context" for full rules (design tokens, banned strings, 4 states, per-session deliverables).
- CSS Modules still acceptable for pre-revamp components; new revamp work uses Tailwind + CSS vars.

## E2E Tests

- Specs in `tests/e2e/specs/`
- Page objects in `tests/e2e/pages/`
- Fixtures in `tests/e2e/fixtures/`
- Config in `playwright.config.ts`
