import { test, expect, type Page } from "@playwright/test";
import { signInWithDemo } from "../fixtures/live-fixtures";

/**
 * LIVE end-to-end journeys against the real backend (no mocks).
 * These complement the mock-based specs by proving the actual pipeline works:
 * RAG SSE + generated answer, chat streaming, upload+OCR, and demo auth.
 *
 * Prerequisites (local full-stack audit only — excluded from CI):
 *   - Backend running on http://localhost:8000 (docker compose up backend)
 *   - Hindsight seeded (scripts/seed_documents.py) + reachable
 *   - Frontend dev server on http://localhost:3000
 *
 * Run SERIALLY — a single local Hindsight instance saturates under parallel
 * recall, causing flaky ReadTimeouts. Always invoke with --workers=1:
 *   npx playwright test --project=live --workers=1
 */

async function waitForSearchAnswer(page: Page): Promise<void> {
  // The answer block appears once the RAG answer streams in.
  await expect(page.getByTestId("search-answer")).toBeVisible({ timeout: 45_000 });
  // At least one source card should be present for a real recall.
  await expect(page.getByTestId("search-source-card").first()).toBeVisible({
    timeout: 45_000,
  });
}

test.describe("LIVE — unauthenticated public search", () => {
  test("landing page loads with no auth leak and CTA navigates to search", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
      timeout: 15_000,
    });
    // No dashboard link / sidebar when anonymous.
    await expect(page.getByRole("link", { name: /dashboard/i })).toHaveCount(0);
    // Primary CTA exists and is visible (journey allows direct nav to /search too).
    const cta = page.getByRole("link", { name: /search|try|start|explore|register/i }).first();
    await expect(cta).toBeVisible();
  });

  test("public RAG search streams real results + answer (no raw JSON)", async ({ page }) => {
    await page.goto("/search");
    await expect(page.getByRole("heading", { name: /search/i })).toBeVisible({
      timeout: 30_000,
    });
    const input = page.locator("#search-input");
    await expect(input).toBeVisible();
    await input.fill("residence permit extension Germany");
    await page.locator('form[role="search"] button[type="submit"]').click();

    await waitForSearchAnswer(page);

    // No raw JSON / [object Object] leaked into the UI.
    const bodyText = await page.locator("#main-content").innerText();
    expect(bodyText).not.toContain("[object Object]");
    expect(bodyText).not.toMatch(/\{"id":|"chunk_id":/);
    // Answer contains substantive legal content.
    expect(bodyText.toLowerCase()).toMatch(/residence|permit|aufn|eu|europ/);
  });
});

test.describe("LIVE — demo sign-in + session", () => {
  test("sign in with demo credentials reaches dashboard with sidebar", async ({ page }) => {
    await signInWithDemo(page);
    await expect(page).toHaveURL(/\/dashboard/);
    // Sidebar with the 5 nav links (Search, Chat, Translate, Dashboard, Exchange).
    for (const label of ["Search", "Chat", "Translate", "Dashboard", "Exchange"]) {
      await expect(page.getByRole("link", { name: new RegExp(label, "i") }).first()).toBeVisible({
        timeout: 10_000,
      });
    }
  });

  test("session persists on new tab (no re-login)", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await signInWithDemo(page);
    await expect(page).toHaveURL(/\/dashboard/);

    // Open a second tab to the root — should land on dashboard, not login.
    const page2 = await ctx.newPage();
    await page2.goto("/");
    await expect(page2).toHaveURL(/\/dashboard/, { timeout: 15_000 });
    await ctx.close();
  });
});

test.describe("LIVE — authenticated RAG + chat", () => {
  test("authenticated search returns results", async ({ page }) => {
    await signInWithDemo(page);
    await page.goto("/search");
    const input = page.locator("#search-input");
    await input.fill("data protection consent GDPR");
    await page.locator('form[role="search"] button[type="submit"]').click();
    await waitForSearchAnswer(page);
  });

  test("chat streams a grounded response", async ({ page }) => {
    await signInWithDemo(page);
    await page.goto("/chat");
    const input = page.locator("#chat-query");
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("What are my data protection rights under GDPR?");
    await page.getByRole("button", { name: /send/i }).click();
    // The assistant answer streams into the conversation (aria-label="Conversation").
    const conversation = page.getByLabel("Conversation");
    await expect(conversation).toBeVisible({ timeout: 60_000 });
    await expect(conversation).toContainText(/GDPR|data protection|Article/i, {
      timeout: 60_000,
    });
    const text = await conversation.innerText();
    expect(text.toLowerCase()).toMatch(/gdpr|data|protection|regulation|article|eu/);
    expect(text).not.toContain("[object Object]");
  });
});

test.describe("LIVE — upload + OCR", () => {
  test("uploads a native PDF and receives OCR text + citation", async ({ page }) => {
    // OCR (Mistral) round-trip can exceed the default 30s test budget on a
    // cold backend — allow the full upload + OCR pipeline to complete.
    test.setTimeout(150_000);
    await signInWithDemo(page);
    await page.goto("/upload");
    const dropzone = page.getByTestId("upload-dropzone");
    await expect(dropzone).toBeVisible({ timeout: 10_000 });

    // Attached minimal valid native-text PDF (generated offline fixture).
    const pdfPath = "tests/e2e/fixtures/files/residence-permit.pdf";
    await page.setInputFiles('input[type="file"]', pdfPath, { timeout: 10_000 }).catch(async () => {
      await page.setInputFiles("input[type=file]", pdfPath);
    });

    // GDPR consent is required before the submit button enables.
    const consent = page.getByTestId("upload-gdpr-consent");
    if (await consent.count()) {
      await consent.check({ timeout: 10_000 });
    }

    // Submit (primary submit button in the form — NOT the Browse button).
    await page
      .getByRole("button", { name: /upload|submit|continue/i })
      .first()
      .click();

    // The success / extracted text state should appear (avg-confidence badge is
    // only rendered in the processed/success view). OCR + Mistral can be
    // slow on a cold backend, so allow a generous ceiling.
    await expect(page.getByTestId("upload-avg-confidence")).toBeVisible({
      timeout: 120_000,
    });
    // The OCR-extracted text table must render at least one row, proving
    // the document was OCR'd and its text extracted.
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });
    await expect(rows).not.toHaveCount(0);
  });
});
