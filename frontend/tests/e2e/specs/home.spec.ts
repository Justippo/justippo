import { test, expect } from "@playwright/test";
import { mockHealthyApi, mockUnauthenticatedSession } from "../fixtures/health-mock";

test.describe("Home page", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await mockUnauthenticatedSession(page);
  });

  test("renders headline and CTA links", async ({ page }) => {
    await page.goto("/");
    const headline = page.locator("h1");
    await expect(headline).toBeVisible();
    await expect(page.getByRole("link", { name: "Get started free" })).toBeVisible();
    await expect(page.getByRole("link", { name: "See how it works" })).toBeVisible();
  });

  test("primary CTA navigates to /register", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Get started free" }).click();
    await expect(page).toHaveURL(/\/register/);
  });

  test("secondary CTA scrolls to how-it-works section", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "See how it works" }).click();
    await expect(page).toHaveURL(/#how-it-works/);
  });
});
