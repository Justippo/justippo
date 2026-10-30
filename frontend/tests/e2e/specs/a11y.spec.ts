import { test } from "../fixtures/a11y";
import { mockHealthyApi } from "../fixtures/health-mock";
import { injectAuthSession } from "../fixtures/auth";

const PUBLIC_ROUTES = [
  { name: "landing", path: "/" },
  { name: "login", path: "/login" },
  { name: "register", path: "/register" },
  { name: "onboarding", path: "/onboarding" },
  { name: "public corpus", path: "/public" },
  { name: "search", path: "/search" },
  { name: "chat", path: "/chat" },
  { name: "viewer", path: "/viewer" },
] as const;

const AUTHENTICATED_ROUTES = [
  { name: "translation", path: "/translation" },
  { name: "fresh translation", path: "/translation?start=upload" },
  { name: "dashboard", path: "/dashboard" },
  { name: "settings", path: "/settings" },
  { name: "legacy upload redirect", path: "/upload" },
  { name: "legacy compare redirect", path: "/compare" },
  { name: "exchange", path: "/exchange" },
] as const;

test.describe("Accessibility (axe-core WCAG 2.1 AA)", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
  });

  for (const route of PUBLIC_ROUTES) {
    test(`${route.name} has zero WCAG 2.1 AA violations`, async ({ page, assertNoViolations }) => {
      await page.goto(route.path);
      await page.waitForLoadState("networkidle");
      await assertNoViolations();
    });
  }

  for (const route of AUTHENTICATED_ROUTES) {
    test(`${route.name} has zero WCAG 2.1 AA violations`, async ({ page, assertNoViolations }) => {
      await injectAuthSession(page);
      await page.goto(route.path);
      await page.waitForLoadState("networkidle");
      await assertNoViolations();
    });
  }
});
