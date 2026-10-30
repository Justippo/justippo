import type { Page } from "@playwright/test";

/** Mock health endpoint so ConnectingOverlay does not block page content in E2E. */
export async function mockHealthyApi(page: Page): Promise<void> {
  await page.route("**/api/v1/health/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "healthy" }),
    })
  );
}

/** Mock Matrix auth session as unauthenticated. RequireAuth redirects to /login. */
export async function mockUnauthenticatedSession(page: Page): Promise<void> {
  await page.route("**/api/v1/auth/matrix/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: false }),
    })
  );
}

/** Mock Matrix auth session as authenticated. RequireAuth allows access. */
export async function mockAuthenticatedSession(page: Page): Promise<void> {
  await page.route("**/api/v1/auth/matrix/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        user_id: "@test:evidence.eu",
        device_id: "TEST_DEVICE",
      }),
    })
  );
  await page.route("**/api/v1/auth/matrix/logout", (route) =>
    route.fulfill({ status: 200, body: "{}" })
  );
}
