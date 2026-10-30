import { test, expect, type Page } from "@playwright/test";
import { LoginPage } from "../pages/login-page";
import { mockHealthyApi } from "../fixtures/health-mock";

/**
 * Mock health + Matrix auth session as unauthenticated.
 * RequireAuth will redirect to /login for protected routes.
 */
async function mockUnauthenticated(page: Page): Promise<void> {
  await mockHealthyApi(page);
  await page.route("**/api/v1/auth/matrix/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: false }),
    })
  );
}

/**
 * Mock health + Matrix auth session as authenticated.
 * RequireAuth will allow access to protected routes.
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
  await page.route("**/api/v1/auth/matrix/logout", (route) =>
    route.fulfill({ status: 200, body: "{}" })
  );
}

test.describe("Login page & auth guard", () => {
  let loginPage: LoginPage;

  test("redirects unauthenticated legacy upload entry to login via Translate", async ({ page }) => {
    loginPage = new LoginPage(page);
    await mockUnauthenticated(page);
    await page.goto("/upload");
    await expect(page).toHaveURL(/\/login\?redirect=%2Ftranslation/, { timeout: 15_000 });
    await expect(loginPage.heading).toBeVisible();
  });

  test("login page shows heading and submit action", async ({ page }) => {
    loginPage = new LoginPage(page);
    await mockUnauthenticated(page);
    await loginPage.goto();
    await expect(loginPage.heading).toBeVisible();
    // In Matrix auth mode, the submit button is "Continue securely"
    // In legacy mode, it shows email/password fields + submit button
    const matrixBtn = loginPage.matrixSubmitBtn;
    const legacyBtn = loginPage.submitBtn;
    const hasMatrix = await matrixBtn.isVisible().catch(() => false);
    const hasLegacy = await legacyBtn.isVisible().catch(() => false);
    expect(hasMatrix || hasLegacy).toBe(true);
  });

  test("authenticated user sees logout in nav", async ({ page }) => {
    loginPage = new LoginPage(page);
    await mockAuthenticated(page);
    await page.goto("/dashboard");
    await expect(loginPage.navLogoutBtn).toBeVisible({ timeout: 15_000 });
    await expect(loginPage.navLoginBtn).toBeHidden();
  });

  test("logout clears session and nav shows sign in", async ({ page }) => {
    loginPage = new LoginPage(page);
    // Start authenticated
    await mockAuthenticated(page);
    await page.goto("/dashboard");
    await expect(loginPage.navLogoutBtn).toBeVisible({ timeout: 15_000 });

    // Switch to unauthenticated for the post-logout state
    await page.unroute("**/api/v1/auth/matrix/session");
    await page.route("**/api/v1/auth/matrix/session", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: false }),
      })
    );

    await loginPage.logoutFromNav();
    await expect(page).toHaveURL(/\/login(?:\?|$)/, { timeout: 15_000 });
    await expect(loginPage.heading).toBeVisible();
    await expect(loginPage.navLogoutBtn).toBeHidden();
  });

  test("authenticated user reaches the canonical flow from a legacy upload URL", async ({
    page,
  }) => {
    loginPage = new LoginPage(page);
    await mockAuthenticated(page);
    await page.goto("/upload");
    await expect(page).toHaveURL(/\/translation\?start=upload/, { timeout: 15_000 });
    await expect(page.getByTestId("upload-dropzone")).toBeVisible({ timeout: 15_000 });
  });

  test("anonymous citation prompts for sign in and returns to the source gate", async ({
    page,
  }) => {
    loginPage = new LoginPage(page);
    const sourceUrl = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";
    const citationParams = new URLSearchParams({
      source: sourceUrl,
      title: "Directive 2004/38/EC",
    });

    // Start unauthenticated — citation page shows sign-in CTA
    await mockUnauthenticated(page);
    await page.goto(`/citation?${citationParams.toString()}`);

    await expect(page.getByRole("heading", { name: "Directive 2004/38/EC" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create account" })).toBeVisible();
    await page.locator("#main-content").getByRole("link", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/login\?redirect=/);

    // Switch to authenticated — citation page shows the official source link
    await page.unroute("**/api/v1/auth/matrix/session");
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
    await page.evaluate(() => {
      localStorage.setItem("evidenceeu_auth", "true");
    });

    // Navigate back to the citation page
    await page.goto(`/citation?${citationParams.toString()}`);
    await expect(page.getByRole("link", { name: /Open official document/ })).toHaveAttribute(
      "href",
      sourceUrl
    );
  });
});
