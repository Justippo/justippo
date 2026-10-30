import { type Page } from "@playwright/test";
import { mockHealthyApi, mockAuthenticatedSession } from "./health-mock";

/**
 * Inject an authenticated session for E2E tests.
 *
 * With MATRIX_AUTH_PREVIEW_ENABLED=true (production builds), the app checks
 * /api/v1/auth/matrix/session on mount — localStorage alone is not enough.
 * This fixture mocks both the health endpoint and the Matrix session as
 * authenticated, plus sets localStorage for backward compatibility.
 */
export async function injectAuthSession(page: Page) {
  await mockHealthyApi(page);
  await mockAuthenticatedSession(page);
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("evidenceeu_auth", "true");
  });
}
