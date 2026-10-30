import { test, expect } from "@playwright/test";
import { mockHealthyApi, mockUnauthenticatedSession } from "../fixtures/health-mock";

test.describe("Reduced motion", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await mockUnauthenticatedSession(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
  });

  test("landing reveal sections are visible without scrolling", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const sections = page.locator("main section");
    await expect(sections.first()).toBeVisible();

    const count = await sections.count();
    expect(count).toBeGreaterThanOrEqual(4);

    await expect
      .poll(async () => {
        const opacities = await sections.evaluateAll((elements) =>
          elements.map((el) => Number(window.getComputedStyle(el).opacity))
        );
        return opacities.every((opacity) => opacity >= 1);
      })
      .toBe(true);
  });

  test("hero content is visible immediately with reduced motion", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByRole("link", { name: "Get started free" })).toBeVisible();
    await expect(page.getByRole("link", { name: "See how it works" })).toBeVisible();
  });
});
