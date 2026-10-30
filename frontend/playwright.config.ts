import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;
const IS_BROWSERSTACK = process.env.BROWSERSTACK === "true";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const IS_REMOTE = !BASE_URL.startsWith("http://localhost");
const LOCAL_PORT = new URL(BASE_URL).port || "3000";

export default defineConfig({
  testDir: "./tests/e2e/specs",
  outputDir: "./test-results",
  timeout: IS_REMOTE ? 60_000 : 30_000,
  expect: { timeout: IS_REMOTE ? 15_000 : 10_000 },
  fullyParallel: true,
  forbidOnly: CI,
  retries: IS_BROWSERSTACK ? 1 : CI ? 2 : 0,
  workers: IS_BROWSERSTACK ? 1 : CI ? 4 : 2,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    actionTimeout: IS_REMOTE ? 15_000 : 10_000,
    navigationTimeout: IS_REMOTE ? 30_000 : 30_000,
  },
  projects: IS_BROWSERSTACK
    ? [{ name: "browserstack", use: {} }]
    : CI
      ? [
          {
            name: "chromium",
            use: { ...devices["Desktop Chrome"] },
            // Local full-stack audit spec (live.integration.spec.ts) needs a
            // real backend + seeded Hindsight — never run in CI.
            testIgnore: ["**/live.integration.spec.ts"],
          },
          {
            name: "firefox",
            use: { ...devices["Desktop Firefox"] },
            testIgnore: ["**/live.integration.spec.ts"],
          },
          {
            name: "webkit",
            use: { ...devices["Desktop Safari"] },
            testIgnore: ["**/live.integration.spec.ts"],
          },
        ]
      : [
          {
            name: "chromium",
            use: { ...devices["Desktop Chrome"] },
            testIgnore: ["**/live.integration.spec.ts"],
          },
          // Local-only full-stack audit project: runs live.integration.spec.ts
          // against the real backend (localhost:8000) + seeded Hindsight.
          // Invoke explicitly: npx playwright test live.integration --project=live
          ...(CI
            ? []
            : [
                {
                  name: "live",
                  use: { ...devices["Desktop Chrome"] },
                  testMatch: ["**/live.integration.spec.ts"],
                },
              ]),
        ],
  webServer: BASE_URL.startsWith("http://localhost")
    ? {
        command: `npx serve out --listen ${LOCAL_PORT} --no-clipboard`,
        url: BASE_URL,
        reuseExistingServer: !CI,
        timeout: 120_000,
      }
    : undefined,
});
