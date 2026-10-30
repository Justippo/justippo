/**
 * File factories for E2E upload tests.
 *
 * All factories use setInputFiles on the hidden #file-input element.
 * Playwright's setInputFiles works on hidden inputs via CDP, bypassing
 * CSS visibility — this is intentional and cross-browser safe.
 *
 * WebKit note: WebKit dispatches the file input `change` event
 * asynchronously (next microtask tick), so React's state update may not
 * have committed to the DOM by the time a subsequent assertion runs.
 * Each helper therefore waits for the expected DOM change before returning,
 * making the helpers safe on all three engines (Chromium, Firefox, WebKit).
 */

import type { Page } from "@playwright/test";

/** Set an oversized PDF (16 MB) — triggers client-side size rejection */
export async function setOversizedFile(page: Page): Promise<void> {
  await page.waitForTimeout(500);
  await page.locator('input[type="file"]').setInputFiles({
    name: "oversized.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(16 * 1024 * 1024),
  });
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="upload-error"]');
      return el && el.textContent && el.textContent.trim().length > 0;
    },
    { timeout: 10_000 }
  );
}

/** Set an unsupported file type — triggers client-side type rejection */
export async function setUnsupportedFile(page: Page): Promise<void> {
  await page.waitForTimeout(500);
  await page.locator('input[type="file"]').setInputFiles({
    name: "document.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("plain text content"),
  });
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="upload-error"]');
      return el && el.textContent && el.textContent.trim().length > 0;
    },
    { timeout: 10_000 }
  );
}

/** Set a valid small PDF — passes client-side validation */
export async function setValidFile(page: Page, filename = "test.pdf"): Promise<void> {
  await page.waitForTimeout(500); // Wait for React hydration
  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 minimal test fixture"),
  });
  // Wait for the cancel button to appear (React state=selected committed).
  // WebKit fires the change event in the next microtask; without this wait
  // the cancelBtn assertion races the React re-render and intermittently fails.
  await page.waitForSelector('button:has-text("Cancel")', {
    state: "visible",
    timeout: 10_000,
  });
}
