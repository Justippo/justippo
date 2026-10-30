import { test, expect, type Page } from "@playwright/test";
import { mockHealthyApi, mockUnauthenticatedSession } from "../fixtures/health-mock";

/**
 * Simulate an authenticated session without navigating first.
 * Uses addInitScript so localStorage is set before page JS runs
 * (unlike evaluate which runs after page load).
 */
async function mockAuthenticated(page: Page): Promise<void> {
  await mockHealthyApi(page);
  await page.addInitScript(() => {
    localStorage.setItem("evidenceeu_auth", "true");
  });
  await page.route("**/api/v1/auth/matrix/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user_id: "@test:evidence.eu",
        device_id: "TEST_DEVICE",
      }),
    })
  );
}

test.describe("Navigation layout", () => {
  test("sidebar shows all 5 nav links when authenticated", async ({ page }) => {
    await mockAuthenticated(page);
    await page.goto("/dashboard");

    // Sidebar is always visible on desktop via CSS.
    // aria-hidden is now correctly false on desktop viewport (768px+).
    const sidebar = page.getByLabel("Sidebar navigation");

    await expect(sidebar.getByRole("link", { name: "Search" })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Chat" })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Translate" })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Exchange" })).toBeVisible();
  });

  test("EvidenceEU brand link navigates to /dashboard when authenticated", async ({
    page,
  }) => {
    await mockAuthenticated(page);
    await page.goto("/translation?start=upload");

    await page.getByLabel("EvidenceEU home").click();

    await expect(page).toHaveURL("/dashboard");
  });

  test("EvidenceEU brand link navigates to / when not authenticated", async ({
    page,
  }) => {
    await mockHealthyApi(page);
    await mockUnauthenticatedSession(page);
    await page.goto("/login");

    await page.getByLabel("EvidenceEU home").click();

    await expect(page).toHaveURL("/");
  });
});

test.describe("Top navbar", () => {
  test("does not render primary nav links when authenticated", async ({ page }) => {
    await mockAuthenticated(page);
    await page.goto("/dashboard");

    // The aria-label="Main navigation" nav was removed from NavigationBar.
    // Verify no search/chat/translate/dashboard/exchange links exist inside
    // the header element.
    const header = page.locator("header");
    await expect(header.getByRole("link", { name: "Search" })).toHaveCount(0);
    await expect(header.getByRole("link", { name: "Chat" })).toHaveCount(0);
    await expect(header.getByRole("link", { name: "Translate" })).toHaveCount(0);
  });

  test("shows sign in link on landing page when not authenticated", async ({ page }) => {
    await mockHealthyApi(page);
    await mockUnauthenticatedSession(page);
    await page.goto("/");

    // Landing page uses AnonymousLayout — sign-in link uses className not testid.
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  });

  test("shows sign out when authenticated", async ({ page }) => {
    await mockAuthenticated(page);
    await page.goto("/dashboard");

    await expect(page.getByTestId("nav-btn-logout")).toBeVisible();
  });
});
