// SPDX-License-Identifier: MIT

import { type Page } from "@playwright/test";
import { test, expect } from "../fixtures/a11y";
import { injectAuthSession } from "../fixtures/auth";
import { mockHealthyApi } from "../fixtures/health-mock";
import { mockUploadSuccess } from "../fixtures/api-mocks";

async function injectTranslationData(page: Page): Promise<void> {
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({
        documentId: "550e8400-e29b-41d4-a716-446655440000",
        filename: "residence-permit.pdf",
        sourceLang: "en",
        targetLang: "de",
        sourcePages: [{ page: 1, text: "Extracted text content." }],
      })
    );
  });
}

test.describe("Contextual translation comparison", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await injectAuthSession(page);
    await mockUploadSuccess(page);
    await injectTranslationData(page);
  });

  test("legacy Compare route opens the canonical aligned comparison", async ({ page }) => {
    await page.goto("/compare");

    await expect(page).toHaveURL(/\/translation\?view=compare/);
    await expect(page.getByRole("heading", { name: "Translation result" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("button", { name: "Compare" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await expect(page.getByTestId("viewer-panel-original")).toBeVisible();
    await expect(page.getByTestId("viewer-panel-translated")).toBeVisible();
  });

  test("switches between focused translation and comparison modes", async ({ page }) => {
    await page.goto("/translation?view=compare");
    await expect(page.getByTestId("viewer-panel-original")).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Translation" }).click();
    await expect(page.getByTestId("viewer-panel-original")).toHaveCount(0);
    await expect(page.getByTestId("viewer-panel-translated")).toBeVisible();

    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page.getByTestId("viewer-panel-original")).toBeVisible();
  });

  test("mode controls are keyboard reachable", async ({ page }) => {
    await page.goto("/translation?view=compare");
    const translationMode = page.getByRole("button", { name: "Translation" });
    await expect(translationMode).toBeVisible({ timeout: 15_000 });

    await translationMode.focus();
    await expect(translationMode).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(translationMode).toHaveAttribute("aria-pressed", "true");
  });

  test("both result modes have zero WCAG 2.1 AA violations", async ({
    page,
    assertNoViolations,
  }) => {
    await page.goto("/translation?view=compare");
    await expect(page.getByTestId("viewer-panel-translated")).toBeVisible({ timeout: 15_000 });
    await assertNoViolations();

    await page.getByRole("button", { name: "Translation" }).click();
    await expect(page.getByTestId("viewer-panel-original")).toHaveCount(0);
    await assertNoViolations();
  });
});
