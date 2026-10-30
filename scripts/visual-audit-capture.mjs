/**
 * EvidenceEU Visual Audit — Automated Screenshot Capture
 *
 * Captures 120 screenshots: 10 screens × 3 viewports × 4 states
 * Output: docs/visual-audit/<screen>/<viewport>/<state>.png
 */
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { join } from "path";

const BASE_URL = "https://evidence-eu-frontend.pages.dev";
const OUTPUT_DIR = join(process.cwd(), "docs", "visual-audit");

const VIEWPORTS = {
  mobile: { width: 375, height: 812 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 800 },
};

const SCREENS = [
  { name: "landing", path: "/", auth: false },
  { name: "search-empty", path: "/search", auth: false },
  { name: "chat-logged-out", path: "/chat", auth: false },
  { name: "matrix-login", path: "/upload", auth: false, openModal: true },
  { name: "dashboard", path: "/dashboard", auth: true },
  { name: "upload", path: "/upload", auth: true },
  { name: "translation", path: "/translation", auth: true },
  { name: "compare", path: "/compare", auth: true },
  { name: "settings", path: "/settings", auth: true },
  { name: "exchange", path: "/exchange", auth: true },
];

const STATES = ["loading", "success", "error", "empty"];

let screenshotCount = 0;
const naCells = [];

async function captureScreenshot(page, screen, viewportName, state) {
  const dir = join(OUTPUT_DIR, screen.name, viewportName);
  mkdirSync(dir, { recursive: true });
  const filePath = join(dir, `${state}.png`);

  const vp = VIEWPORTS[viewportName];
  await page.setViewportSize({ width: vp.width, height: vp.height });

  // Set up state-specific route interceptors BEFORE navigation
  if (state === "error") {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: '{"detail":"Internal Server Error"}',
      })
    );
  }

  if (state === "loading") {
    // Block all API calls indefinitely so loading UI persists
    await page.route("**/api/v1/**", () => new Promise(() => {}));
  }

  // Handle auth for logged-in screens
  if (screen.auth) {
    // First visit to set localStorage
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.evaluate(() => localStorage.setItem("evidenceeu_auth", "true"));
  }

  // Handle empty state - clear storage
  if (state === "empty") {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  }

  // Navigate to target screen
  const navTimeout = state === "loading" ? 8000 : 30000;
  const waitUntil = state === "loading" ? "commit" : "networkidle";
  try {
    await page.goto(`${BASE_URL}${screen.path}`, { waitUntil, timeout: navTimeout });
  } catch {
    // Loading state timeout is expected
  }

  // Open login modal for matrix-login screen
  if (screen.openModal) {
    try {
      await page.click('[data-testid="nav-btn-login"]', { timeout: 5000 });
      await page.waitForSelector('[data-testid="matrix-login-overlay"]', {
        state: "visible",
        timeout: 5000,
      });
    } catch {
      // Modal may not open if already in error/loading state
    }
  }

  // Wait for UI to settle
  const settleTimes = { success: 2000, error: 2000, empty: 1500, loading: 1500 };
  await page.waitForTimeout(settleTimes[state] || 1000);

  // For landing success: full-page scroll to trigger animations, then back to top
  if (screen.name === "landing" && state === "success") {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(800);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(800);
  }

  // Take screenshot
  const fullPage = screen.name === "landing" && state === "success";
  await page.screenshot({ path: filePath, fullPage });
  screenshotCount++;
  console.log(`  ✓ ${screen.name}/${viewportName}/${state}.png`);
}

async function main() {
  const totalCells = SCREENS.length * Object.keys(VIEWPORTS).length * STATES.length;
  console.log("EvidenceEU Visual Audit — Screenshot Capture");
  console.log(`Target: ${BASE_URL}`);
  console.log(`Output: ${OUTPUT_DIR}`);
  console.log(`Cells: ${SCREENS.length} screens × ${Object.keys(VIEWPORTS).length} viewports × ${STATES.length} states = ${totalCells}\n`);

  const browser = await chromium.launch({ headless: true });

  for (const screen of SCREENS) {
    console.log(`\n📸 ${screen.name} (${screen.auth ? "auth" : "anon"})`);
    for (const vpName of Object.keys(VIEWPORTS)) {
      for (const state of STATES) {
        const context = await browser.newContext();
        const page = await context.newPage();
        try {
          await captureScreenshot(page, screen, vpName, state);
        } catch (e) {
          console.error(`  ✗ ${screen.name}/${vpName}/${state}: ${e.message.split("\n")[0]}`);
          naCells.push(`${screen.name}/${vpName}/${state}`);
        }
        await context.close();
      }
    }
  }

  await browser.close();

  console.log(`\n${"=".repeat(60)}`);
  console.log(`Screenshots captured: ${screenshotCount} / ${totalCells}`);
  console.log(`N/A cells: ${naCells.length}`);
  if (naCells.length > 0) console.log(`N/A list: ${naCells.join(", ")}`);
}

main().catch(console.error);
