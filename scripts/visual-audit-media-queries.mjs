/**
 * EvidenceEU Visual Audit — Media Query Verification Screenshots
 * T3A: prefers-reduced-motion
 * T3B: prefers-reduced-transparency
 */
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { join } from "path";

const BASE_URL = "https://evidence-eu-frontend.pages.dev";
const OUTPUT_DIR = join(process.cwd(), "docs", "visual-audit");

async function main() {
  const browser = await chromium.launch({ headless: true });

  // ── T3A: prefers-reduced-motion ──────────────────────────────────
  console.log("T3A: prefers-reduced-motion — landing/desktop");
  const ctxMotion = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: "reduce",
  });
  const pageMotion = await ctxMotion.newPage();
  const motionErrors = [];
  pageMotion.on("console", (msg) => {
    if (msg.type() === "error") motionErrors.push(msg.text());
  });

  await pageMotion.goto(BASE_URL, { waitUntil: "networkidle", timeout: 30000 });
  await pageMotion.waitForTimeout(2000);

  // Scroll full page and back to trigger any scroll animations
  await pageMotion.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await pageMotion.waitForTimeout(1500);
  await pageMotion.evaluate(() => window.scrollTo(0, 0));
  await pageMotion.waitForTimeout(1000);

  const dirMotion = join(OUTPUT_DIR, "landing", "desktop");
  mkdirSync(dirMotion, { recursive: true });
  await pageMotion.screenshot({
    path: join(dirMotion, "reduced-motion.png"),
    fullPage: true,
  });
  console.log(`  ✓ reduced-motion.png`);
  console.log(`  JS console errors: ${motionErrors.length}`);
  motionErrors.forEach((e) => console.log(`    ERR: ${e}`));
  await ctxMotion.close();

  // ── T3B: prefers-reduced-transparency ────────────────────────────
  console.log("\nT3B: prefers-reduced-transparency — dashboard/desktop");
  const ctxTransp = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  const pageTransp = await ctxTransp.newPage();

  // Set auth first
  await pageTransp.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 15000 });
  await pageTransp.evaluate(() => localStorage.setItem("evidenceeu_auth", "true"));

  // Use CDP to emulate prefers-reduced-transparency
  const cdp = await ctxTransp.newCDPSession(pageTransp);
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-transparency", value: "reduce" }],
  });

  await pageTransp.goto(`${BASE_URL}/dashboard`, {
    waitUntil: "networkidle",
    timeout: 30000,
  });
  await pageTransp.waitForTimeout(2500);

  const dirTransp = join(OUTPUT_DIR, "dashboard", "desktop");
  mkdirSync(dirTransp, { recursive: true });
  await pageTransp.screenshot({
    path: join(dirTransp, "reduced-transparency.png"),
  });
  console.log(`  ✓ reduced-transparency.png`);
  await ctxTransp.close();

  await browser.close();
  console.log("\nMedia query verification complete.");
}

main().catch(console.error);
