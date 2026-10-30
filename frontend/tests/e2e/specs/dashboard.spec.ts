import { expect, test } from "@playwright/test";
import { injectAuthSession } from "../fixtures/auth";
import { mockHealthyApi } from "../fixtures/health-mock";

test.describe("Dashboard privacy contract", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await injectAuthSession(page);
    await page.goto("/dashboard");
  });

  test("shows real actions and ephemeral-processing guidance", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Private by design" })).toBeVisible();
    await expect(page.getByText(/processed ephemerally/i)).toBeVisible();
    await expect(page.getByRole("link", { name: "Translate document" })).toHaveAttribute(
      "href",
      "/translation?start=upload"
    );
    await expect(page.getByText("System Status")).toBeVisible();
  });

  test("does not claim persisted workspace history", async ({ page }) => {
    await expect(page.getByText("Recent documents")).toHaveCount(0);
    await expect(page.getByText("Recent searches")).toHaveCount(0);
    await expect(page.getByText("Recent Activity")).toHaveCount(0);
    await expect(page.getByText("Sample Document")).toHaveCount(0);
    await expect(page.getByText("GDPR compliance")).toHaveCount(0);
  });
});
