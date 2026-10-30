// SPDX-License-Identifier: MIT
/**
 * E2E Tests — Multilingual Output Viewer (Issue #18)
 *
 * Tests:
 * 1. Viewer page loads with correct layout
 * 2. Language selector switches translation
 * 3. GDPR header is sent with every API request
 * 4. Keyboard navigation works (Tab through panels)
 * 5. Truncated banner appears when translation is partial
 */

import { test, expect, type Page } from "@playwright/test";
import { injectAuthSession } from "../fixtures/auth";
import { mockHealthyApi } from "../fixtures/health-mock";

const VIEWER_ROUTE = "/viewer";

const MOCK_TRANSLATED_PAGES_DE = [
  { page: 1, text: "EU-Aufenthaltstitel-Antragsformular. Name: John Doe." },
  { page: 2, text: "Anhang A: Erforderliche Dokumente für grenzüberschreitende Anwendung." },
];

const MOCK_TRANSLATED_PAGES_FR = [
  { page: 1, text: "Formulaire de demande de titre de séjour UE." },
  { page: 2, text: "Annexe A: Documents requis pour demande transfrontalière." },
];

async function injectSessionData(page: Page) {
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({
        documentId: "550e8400-e29b-41d4-a716-446655440000",
        filename: "residence-permit.pdf",
        sourceLang: "en",
        targetLang: "de",
        pageCount: 2,
        sourcePages: [
          { page: 1, text: "EU Residence Permit Application Form. Name: John Doe." },
          { page: 2, text: "Appendix A: Required documents for cross-border application." },
        ],
      })
    );
  });
}

test.describe("Multilingual Output Viewer", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await injectAuthSession(page);

    await page.route("**/api/v1/translate/", async (route) => {
      const body = route.request().postDataJSON();
      const targetLang = body?.target_language ?? "de";
      const translated = targetLang === "fr" ? MOCK_TRANSLATED_PAGES_FR : MOCK_TRANSLATED_PAGES_DE;
      await route.fulfill({
        status: 200,
        json: {
          job_id: `job-${targetLang}-001`,
          status: "done",
          translated_pages: translated,
        },
      });
    });
  });

  test("viewer page loads with correct layout", async ({ page }) => {
    await injectSessionData(page);
    await page.goto(VIEWER_ROUTE);

    await expect(page.getByTestId("viewer-title")).toBeVisible();
    await expect(page.getByTestId("viewer-title")).toHaveText("Translation result");

    await expect(page.getByTestId("viewer-filename")).toContainText("residence-permit.pdf");

    await expect(page.getByTestId("viewer-panel-translated").first()).toBeVisible();
    await expect(page.getByTestId("viewer-panel-original")).toHaveCount(0);

    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page.getByTestId("viewer-panel-original").first()).toBeVisible();

    const panels = page.getByTestId("viewer-panels");
    await expect(panels).toBeVisible();
  });

  test("language selector switches translation", async ({ page }) => {
    await injectSessionData(page);
    await page.goto(VIEWER_ROUTE);

    await expect(page.getByTestId("viewer-lang")).toHaveValue("de");

    await page.getByTestId("viewer-lang").selectOption("fr");

    await expect(page.getByTestId("viewer-panel-translated").first()).toContainText("Formulaire", {
      timeout: 10000,
    });

    await expect(page.getByTestId("viewer-lang")).toHaveValue("fr");
  });

  test("GDPR header is sent with every API request", async ({ page }) => {
    await injectSessionData(page);
    await page.goto(VIEWER_ROUTE);

    // Wait for the initial auto-translate to finish rendering the toolbar before
    // swapping the route, otherwise the in-flight request races with unroute().
    await expect(page.getByTestId("viewer-lang")).toBeVisible({ timeout: 10000 });

    let gdprHeaderFound = false;

    await page.unroute("**/api/v1/translate/");
    await page.route("**/api/v1/translate/", async (route) => {
      const headers = route.request().headers();
      if (headers["x-gdpr-consent"]) {
        gdprHeaderFound = true;
      }
      await route.fulfill({
        status: 200,
        json: { job_id: "job-test", status: "done", translated_pages: [] },
      });
    });

    await page.getByTestId("viewer-lang").selectOption("fr");
    await page.waitForTimeout(2000);

    expect(gdprHeaderFound).toBe(true);
  });

  test("keyboard navigation reaches the language selector via Tab", async ({ page }) => {
    await injectSessionData(page);
    await page.goto(VIEWER_ROUTE);

    const selector = page.getByTestId("viewer-lang");

    // WCAG 2.1.1 (Keyboard): a keyboard-only user must be able to Tab to the
    // viewer's primary interactive control. We assert reachability by walking
    // Tab from the document start rather than checking activeElement.tagName
    // after a single Tab — WebKit/Safari deliberately excludes buttons and
    // links from default Tab traversal (the OS "Full Keyboard Access" setting),
    // so a single-Tab tag assertion is engine-dependent. A native <select> is
    // tabbable in every engine, making this deterministic on Chromium, Firefox
    // and WebKit alike.
    let reached = false;
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press("Tab");
      if (await selector.evaluate((el) => el === document.activeElement)) {
        reached = true;
        break;
      }
    }

    expect(reached).toBe(true);
    await expect(selector).toBeFocused();
  });

  test("truncated banner appears when translation is partial", async ({ page }) => {
    await injectSessionData(page);
    await page.goto(VIEWER_ROUTE);

    // Wait for the initial auto-translate to finish rendering the toolbar before
    // swapping the route, otherwise the in-flight request races with unroute().
    await expect(page.getByTestId("viewer-lang")).toBeVisible({ timeout: 10000 });

    await page.unroute("**/api/v1/translate/");
    await page.route("**/api/v1/translate/", async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          job_id: "job-trunc-001",
          status: "done",
          translated_pages: [{ page: 1, text: "Only page 1 translated. [truncated]" }],
        },
      });
    });

    await page.getByTestId("viewer-lang").selectOption("fr");

    await expect(page.getByTestId("truncated-banner")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("truncated-banner")).toContainText("Preview limited");
  });
});
