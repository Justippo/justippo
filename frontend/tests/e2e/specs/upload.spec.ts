import { test, expect } from "@playwright/test";
import { UploadPage } from "../pages/upload-page";
import { mockUploadSuccess, mockUploadError } from "../fixtures/api-mocks";
import { setOversizedFile, setUnsupportedFile, setValidFile } from "../fixtures/sample-files";
import { injectAuthSession } from "../fixtures/auth";

test.describe("Upload → OCR → translation flow", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuthSession(page);
  });

  test("rejects oversized files client-side without network call", async ({ page }) => {
    const upload = new UploadPage(page);
    await upload.goto();
    await setOversizedFile(page);
    await expect(upload.errorText).toContainText("above the 4 MB limit", { timeout: 10_000 });
    await expect(upload.submitBtn).toHaveCount(0);
  });

  test("rejects unsupported file types client-side", async ({ page }) => {
    const upload = new UploadPage(page);
    await upload.goto();
    await setUnsupportedFile(page);
    await expect(upload.errorText).toContainText("not a supported file type", {
      timeout: 10_000,
    });
  });

  test("uploads, reviews OCR, selects a language, and translates", async ({ page }) => {
    await mockUploadSuccess(page);
    const upload = new UploadPage(page);
    await upload.goto();
    await setValidFile(page, "passport.pdf");
    await upload.langSelect.selectOption("de");
    const consent = page.getByTestId("upload-gdpr-consent");
    if (await consent.count()) await consent.check();
    await expect(upload.submitBtn).toBeEnabled();
    await upload.submitBtn.click();
    await expect(upload.successHeading).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("translation-target-confirmation")).toContainText("German");
    await upload.continueBtn.click();
    await expect(page.getByRole("heading", { name: "Translated PDF reference" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("region", { name: "PDF reference viewer" })).toBeVisible();
  });

  test("retranslates the original PDF when target language changes on the result screen", async ({
    page,
  }) => {
    await mockUploadSuccess(page);
    const upload = new UploadPage(page);
    await upload.goto();
    await setValidFile(page, "passport.pdf");
    await upload.langSelect.selectOption("de");
    const consent = page.getByTestId("upload-gdpr-consent");
    if (await consent.count()) await consent.check();
    await upload.submitBtn.click();
    await expect(upload.successHeading).toBeVisible({ timeout: 15_000 });
    await upload.continueBtn.click();
    await expect(page.getByRole("heading", { name: "Translated PDF reference" })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByLabel("Target language").selectOption("fr");

    await expect(page.getByRole("heading", { name: "Translating EN → FR" })).toBeVisible();
    await expect(page.getByText("Ce document contient des informations juridiques.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("EN → FR", { exact: true })).toBeVisible();
  });

  test("chooses another PDF after a reference translation error", async ({ page }) => {
    await mockUploadSuccess(page);
    await page.route("**/api/v1/translate/pdf-reference", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: { code: "SERVICE_UNAVAILABLE" } }),
      })
    );
    const upload = new UploadPage(page);
    await upload.goto();
    await setValidFile(page, "passport.pdf");
    await upload.langSelect.selectOption("de");
    const consent = page.getByTestId("upload-gdpr-consent");
    if (await consent.count()) await consent.check();
    await upload.submitBtn.click();
    await expect(upload.successHeading).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("translation-target-confirmation")).toContainText("German");
    await upload.continueBtn.click();
    await expect(page.getByRole("heading", { name: "Translation not completed" })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: "Choose another PDF" }).click();

    await expect(page.getByRole("heading", { name: "Translate document" })).toBeVisible();
  });

  test("cancels a selected file", async ({ page }) => {
    const upload = new UploadPage(page);
    await upload.goto();
    await setValidFile(page);
    await expect(upload.cancelBtn).toBeVisible();
    await upload.cancelBtn.click();
    await expect(upload.submitBtn).toHaveCount(0);
  });

  test("displays backend validation errors", async ({ page }) => {
    await mockUploadError(page, "File processing failed — corrupt PDF");
    const upload = new UploadPage(page);
    await upload.goto();
    await setValidFile(page);
    const consent = page.getByTestId("upload-gdpr-consent");
    if (await consent.count()) await consent.check();
    await upload.submitBtn.click();
    await expect(page.getByTestId("upload-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("upload-error")).toContainText(
      "Upload could not be completed. Check your connection and try again."
    );
  });
});
