import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.LIVE_FRONTEND_URL ?? process.env.PLAYWRIGHT_BASE_URL;

if (!BASE_URL || BASE_URL.startsWith("http://localhost")) {
  throw new Error("LIVE_FRONTEND_URL must point to the deployed frontend");
}

export default defineConfig({
  testDir: "./tests/e2e/live",
  outputDir: "./test-results-live",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "playwright-live-report" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 45_000,
  },
  projects: [{ name: "chromium-live", use: { ...devices["Desktop Chrome"] } }],
});
