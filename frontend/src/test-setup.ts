// SPDX-License-Identifier: MIT
// Global test setup — imports jest-dom matchers (toBeInTheDocument, toHaveAttribute, etc.)
// NOTE: Must import vitest globals BEFORE @testing-library/jest-dom
import { vi, expect, describe, it, beforeEach, afterEach, beforeAll, afterAll } from "vitest";
// Set globals BEFORE importing @testing-library/jest-dom
(globalThis as any).vi = vi;
(globalThis as any).expect = expect;
(globalThis as any).describe = describe;
(globalThis as any).it = it;
(globalThis as any).beforeEach = beforeEach;
(globalThis as any).afterEach = afterEach;
(globalThis as any).beforeAll = beforeAll;
(globalThis as any).afterAll = afterAll;

// Now import jest-dom matchers (vitest-specific entry in v7)
import "@testing-library/jest-dom/vitest";

// Use the global React that was set by vitest (instead of importing from "react")
// This avoids multiple React copies issue
const React = globalThis.React;

// Export for explicit imports
export { React };

class MockIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin = "";
  readonly thresholds: ReadonlyArray<number> = [];

  constructor(
    private readonly callback: IntersectionObserverCallback,
    _options?: IntersectionObserverInit
  ) {}

  observe(target: Element): void {
    this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this);
  }

  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

Object.defineProperty(window, "IntersectionObserver", {
  writable: true,
  value: MockIntersectionObserver,
});

// jsdom does not implement matchMedia — used by dark-mode theme hooks.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    pathname: "/",
    query: {},
    asPath: "/",
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

if (typeof window.localStorage === "undefined" || typeof window.localStorage.clear !== "function") {
  const store: Record<string, string> = {};
  window.localStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k in store) delete store[k];
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
  } as Storage;
}

if (
  typeof window.sessionStorage === "undefined" ||
  typeof window.sessionStorage.clear !== "function"
) {
  const sstore: Record<string, string> = {};
  window.sessionStorage = {
    getItem: (k: string) => sstore[k] ?? null,
    setItem: (k: string, v: string) => {
      sstore[k] = v;
    },
    removeItem: (k: string) => {
      delete sstore[k];
    },
    clear: () => {
      for (const k in sstore) delete sstore[k];
    },
    get length() {
      return Object.keys(sstore).length;
    },
    key: (i: number) => Object.keys(sstore)[i] ?? null,
  } as Storage;
}

// Re-export for explicit imports
export { vi, expect, describe, it, beforeEach, afterEach, beforeAll, afterAll };

// ── i18n mock ─────────────────────────────────────────────────────────────────
// Load English locale so t() resolves keys to real English text instead of
// returning the raw key string. This lets tests use getByText("Translate")
// rather than getByText("nav.translate") — matching real user-visible text.
import en from "./locales/en.json";

// Un-nested locale (all keys are already dot-notation strings).
const enMap = en as Record<string, string>;

vi.mock("@/hooks/useT", () => ({
  useT: () => ({
    t: (key: string, params?: Record<string, string | number>): string => {
      let value = enMap[key];
      if (value === undefined) {
        value = key; // fallback — key itself
      }
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          value = value.replace(new RegExp("\\{" + k + "\\}", "g"), String(v));
        }
      }
      return value;
    },
    changeLanguage: vi.fn(),
    language: "en",
  }),
}));
