import { expect, test } from "@playwright/test";
import { mockHealthyApi, mockUnauthenticatedSession } from "../fixtures/health-mock";

test.describe("BrowserStack cross-browser smoke", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await mockUnauthenticatedSession(page);
  });

  test("loads the public landing page", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByRole("link", { name: "Get started free" })).toBeVisible();
  });

  test("enforces the upload authentication guard", async ({ page }) => {
    await page.goto("/upload");

    await expect(page).toHaveURL(/\/login\?redirect=%2Ftranslation/, { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  test("loads the public search experience", async ({ page }) => {
    await page.goto("/search");

    await expect(page.locator("#search-input")).toBeVisible();
    await expect(
      page.getByText(/Start typing to search|Search public EU legal documents/)
    ).toBeVisible();
  });
});
