import type { Page, Locator } from "@playwright/test";

/**
 * Page Object: Document Viewer page (/exchange)
 */
export class ViewerPage {
  readonly page: Page;
  readonly columnEn: Locator;
  readonly columnDe: Locator;
  readonly toggleEn: Locator;
  readonly toggleDe: Locator;
  readonly prevBtn: Locator;
  readonly nextBtn: Locator;
  readonly pageIndicator: Locator;
  readonly glossaryBtn: Locator;
  readonly glossaryPanel: Locator;
  readonly breadcrumbBack: Locator;

  constructor(page: Page) {
    this.page = page;
    this.columnEn = page.locator('[data-testid="viewer-column-en"]');
    this.columnDe = page.locator('[data-testid="viewer-column-de"]');
    this.toggleEn = page.locator("#btn-lang-en");
    this.toggleDe = page.locator("#btn-lang-de");
    this.prevBtn = page.locator("#btn-prev-page");
    this.nextBtn = page.locator("#btn-next-page");
    this.pageIndicator = page.locator(".dv-page-indicator, [aria-live='polite']").first();
    this.glossaryBtn = page.locator("#btn-view-glossary-history");
    this.glossaryPanel = page.locator("#glossary-panel");
    this.breadcrumbBack = page.locator("#btn-back");
  }

  async goto(): Promise<void> {
    await this.page.goto("/exchange");
  }

  /** Navigate to /exchange with mock document data in sessionStorage */
  async gotoWithMockData(): Promise<void> {
    await this.page.goto("/exchange");
    await this.page.evaluate(() => {
      sessionStorage.setItem(
        "evidence-eu-document-data",
        JSON.stringify({
          documentId: "mock-doc-id",
          filename: "test_document.pdf",
          targetLang: "de",
          sourceLang: "en",
          pageCount: 5,
          sourcePages: [
            { page: 1, text: "First page text content." },
            { page: 2, text: "Second page text content." },
          ],
          translatedPages: [
            { page: 1, text: "Textinhalt der ersten Seite." },
            { page: 2, text: "Textinhalt der zweiten Seite." },
          ],
        })
      );
    });
    await this.page.reload();
  }
}
