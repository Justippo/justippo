import { expect, test } from "@playwright/test";
import { injectAuthSession } from "../fixtures/auth";
import { mockHealthyApi } from "../fixtures/health-mock";

test.describe("Interface language", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await injectAuthSession(page);
    await page.goto("/translation?start=upload");
  });

  test("switches the shell and Translation workflow and persists after reload", async ({
    page,
  }) => {
    const languageSelect = page.getByTestId("interface-language-select");

    await expect(languageSelect).toHaveValue("en");
    await languageSelect.selectOption("de");

    await expect(page.locator("html")).toHaveAttribute("lang", "de");
    await expect(page.getByRole("heading", { name: "Dokument übersetzen" })).toBeVisible();
    await expect(
      page.getByText(
        "Ich willige in die Verarbeitung dieses Dokuments für OCR und Übersetzung ein."
      )
    ).toBeVisible();

    await page.reload();

    await expect(page.getByTestId("interface-language-select")).toHaveValue("de");
    await expect(page.locator("html")).toHaveAttribute("lang", "de");

    await page.getByTestId("interface-language-select").selectOption("fr");
    await expect(page.getByRole("heading", { name: "Traduire un document" })).toBeVisible();
    await expect(
      page.getByText(
        "Je consens au traitement de ce document à des fins de reconnaissance optique de caractères (OCR) et de traduction."
      )
    ).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  });
});
