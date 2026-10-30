import { test, expect } from "@playwright/test";
import { SearchPage } from "../pages/search-page";
import { mockSearchSuccess, mockSearchError } from "../fixtures/api-mocks";
import { mockHealthyApi } from "../fixtures/health-mock";
import { buildSSEStream, parseSSEStream } from "../fixtures/sse-helpers";

test.describe("Search flow", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
  });

  test("renders empty state and allows searching", async ({ page }) => {
    // Block all API requests so no stray EventSource connection can change
    // viewState away from "empty" during the assertions (race condition fix).
    await page.route("**/api/**", (route) => route.abort("blockedbyclient"));
    const search = new SearchPage(page);
    await search.goto();
    // Next.js App Router + useSearchParams() bails out to client-side rendering
    // in static export — the initial HTML is a Suspense fallback (empty div).
    // Wait for the search heading to confirm hydration completed before checking
    // for the empty state container. 30s accounts for macOS ARM64 self-hosted
    // runner JS parsing + hydration latency.
    await expect(
      page.getByRole("heading", { name: /Search documents/i })
    ).toBeVisible({ timeout: 30_000 });
    // Check empty state text directly on the container to avoid cross-assertion races.
    await expect(search.emptyState).toContainText(
      /Search public EU legal documents/,
      { timeout: 15_000 }
    );
  });

  test("displays mocked search results", async ({ page }) => {
    await mockSearchSuccess(page);
    const search = new SearchPage(page);
    await search.goto("EU patient rights");
    await expect(search.answerBlock).toBeVisible({ timeout: 15_000 });
    await expect(search.answerBlock).toContainText("EU Directive 2011/24");
    await expect(search.sourceCards.first()).toBeVisible();
  });

  test("shows error state and allows retry", async ({ page }) => {
    await mockSearchError(page);
    const search = new SearchPage(page);
    await search.goto("trigger error");
    await expect(search.errorBox).toBeVisible({ timeout: 30_000 });
    await expect(search.retryButton).toBeVisible();
  });

  test("SSE stream returns typed events", () => {
    const events = [
      { type: "result" as const, data: { answer: "Hello" } },
      { type: "source" as const, data: { title: "EU Doc" } },
      { type: "done" as const },
    ];
    const stream = buildSSEStream(events);
    const parsed = parseSSEStream(stream);
    expect(parsed).toHaveLength(3);
    expect(parsed[0].type).toBe("result");
    expect(parsed[2].type).toBe("done");
  });

  test("SSE stream surfaces errors before done sentinel", () => {
    const events = [
      { type: "error" as const, data: { message: "RAG timeout" } },
      { type: "done" as const },
    ];
    const parsed = parseSSEStream(buildSSEStream(events));
    expect(parsed[0].type).toBe("error");
    expect(parsed[1].type).toBe("done");
  });
});
