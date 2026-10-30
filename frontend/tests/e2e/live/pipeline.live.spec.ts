import path from "node:path";
import { expect, test } from "@playwright/test";

function withTimeout<T>(promise: Promise<T>, label: string, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`${label} timed out after ${ms}ms`)),
        ms,
      );
      timer.unref?.();
    }),
  ]);
}

function isPipelineRequest(url: string): boolean {
  return ["/api/v1/documents/", "/api/v1/translate/", "/api/v1/search/"].some((pathname) =>
    url.includes(pathname)
  );
}

function sseEventTypes(body: string): readonly string[] {
  return [...body.matchAll(/^event:\s*(.+)$/gm)].map((match) => match[1].trim());
}

test("deployed authenticated OCR, translation, and SSE search pipeline", async ({ page }) => {
  const pipelineRequests: string[] = [];
  let searchBodyPromiseResolve: (body: string) => void;
  const searchBodyPromise = new Promise<string>((resolve) => {
    searchBodyPromiseResolve = resolve;
  });

  // The live pipeline suite verifies product APIs, not the external Matrix
  // authorization provider. Stub only EvidenceEU's opaque session-status
  // boundary; document, translation, and search requests remain fully live.
  await page.route("**/api/v1/auth/matrix/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user_id: "@ci-pipeline:matrix.org",
        device_id: "CI_PIPELINE",
      }),
    });
  });

  // Intercept SSE search responses via route.fetch() — the CDP
  // Network.getResponseBody protocol does not buffer streamed SSE bodies,
  // so page.waitForResponse + response.text() would raise
  // "No data found for resource with given identifier".
  // route.fetch() reads the full stream (including the terminal `done` event)
  // before the browser can discard it.
  await page.route("**/api/v1/search/**", async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    searchBodyPromiseResolve(body);
    await route.fulfill({ response, body });
  });

  page.on("request", (request) => {
    if (isPipelineRequest(request.url())) {
      pipelineRequests.push(request.url());
    }
  });

  await page.goto("/dashboard");
  await expect(page.getByTestId("nav-btn-logout")).toBeVisible();

  await page.goto("/translation?start=upload");
  const uploadResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().includes("/api/v1/documents/")
  );
  await page
    .locator('input[type="file"]')
    .setInputFiles(
      path.resolve(__dirname, "../../../../docs/visual-audit/upload/desktop/success.png")
    );
  await page.getByTestId("upload-gdpr-consent").check();
  await page.getByTestId("translation-lang-select").selectOption("de");
  await page.getByRole("button", { name: "Upload for analysis" }).click();
  const completedUploadResponse = await uploadResponse;
  expect(completedUploadResponse.ok()).toBe(true);
  const uploadResult = (await completedUploadResponse.json()) as {
    readonly pages?: readonly { readonly text?: string }[];
  };
  expect(uploadResult.pages?.some((page) => Boolean(page.text?.trim()))).toBe(true);
  await expect(page.getByText("Document processed")).toBeVisible({ timeout: 60_000 });

  const translationResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().includes("/api/v1/translate/"),
    { timeout: 60_000 }
  );
  await page.getByRole("button", { name: "Continue to translation" }).click();
  const completedTranslationResponse = await translationResponse;
  expect(completedTranslationResponse.ok()).toBe(true);
  const translationResult = (await completedTranslationResponse.json()) as {
    readonly status?: string;
    readonly translated_pages?: readonly { readonly text?: string }[];
  };
  expect(translationResult.status).toBe("done");
  expect(translationResult.translated_pages?.some((page) => Boolean(page.text?.trim()))).toBe(true);
  await expect(page.getByTestId("viewer-panel-translated").first()).toBeVisible({
    timeout: 60_000,
  });

  await page.goto("/search");
  await page.locator("#search-input").fill("residence permit renewal");
  await page.getByRole("button", { name: "Search" }).click();
  const searchBody = await withTimeout(searchBodyPromise, "SSE body", 30_000);

  const eventTypes = sseEventTypes(searchBody);
  expect(eventTypes).toContain("results_complete");
  expect(eventTypes).toContain("done");
  expect(eventTypes).not.toContain("error");

  if (eventTypes.includes("result")) {
    await expect(page.getByTestId("search-source-card").first()).toBeVisible({ timeout: 15_000 });
  } else {
    await expect(page.getByText("No results found. Try different keywords.")).toBeVisible({
      timeout: 15_000,
    });
  }

  expect(pipelineRequests.some((url) => url.includes("/api/v1/documents/"))).toBe(true);
  expect(pipelineRequests.some((url) => url.includes("/api/v1/translate/"))).toBe(true);
  expect(pipelineRequests.some((url) => url.includes("/api/v1/search/"))).toBe(true);
});
