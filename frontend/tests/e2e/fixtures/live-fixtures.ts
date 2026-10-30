import { test as base, type Page, type BrowserContext } from "@playwright/test";
import { DEMO_EMAIL, DEMO_PASSWORD } from "@evidenceeu/shared";

/**
 * Live integration fixtures — drive the REAL backend (no API mocks) so the
 * capstone E2E audit verifies the actual pipeline (RAG SSE + answer, chat
 * streaming, upload+OCR, Matrix/Session auth) end-to-end.
 *
 * Requires the local stack running:
 *   docker compose up -d backend chromadb
 *   (hindsight-evidenceeu running on host, reached via docker-compose.override.yml)
 *   npm run dev  (frontend on :3000)
 */

export async function signInWithDemo(page: Page): Promise<void> {
  await page.goto("/login");
  const email = page.getByTestId("login-email");
  const password = page.getByTestId("login-password");
  const hasForm = (await email.count()) > 0 && (await password.count()) > 0;
  if (hasForm) {
    await email.fill(DEMO_EMAIL);
    await password.fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: /sign in|continue|log ?in/i }).click();
  } else {
    // Matrix preview mode — not expected in default local config, but handle gracefully.
    await page.getByRole("button", { name: /continue|sign in/i }).click();
  }
  // Expect redirect to dashboard (or a protected route) — never stay on /login.
  await page.waitForURL(/\/(dashboard|search|chat|translate|exchange)/, {
    timeout: 20_000,
  });
}

export async function clearLocalAuth(page: Page): Promise<void> {
  await page.evaluate(() => {
    try {
      localStorage.removeItem("evidenceeu_auth");
      sessionStorage.removeItem("evidenceeu_session_v1");
    } catch {
      /* ignore */
    }
  });
}

export const test = base.extend<{
  livePage: Page;
  liveContext: BrowserContext;
}>({
  liveContext: async ({ browser }, use) => {
    const context = await browser.newContext();
    await use(context);
    await context.close();
  },
  livePage: async ({ liveContext }, use) => {
    const page = await liveContext.newPage();
    await clearLocalAuth(page);
    await use(page);
  },
});

export { expect } from "@playwright/test";
