import type { Page, Locator } from "@playwright/test";

export class SearchPage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly searchSubmit: Locator;
  readonly answerBlock: Locator;
  readonly sourceList: Locator;
  readonly sourceCards: Locator;
  readonly errorBox: Locator;
  readonly retryButton: Locator;
  readonly resultsHeader: Locator;
  readonly emptyState: Locator;
  readonly loadingState: Locator;
  readonly resultCards: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.locator("#search-input");
    this.searchSubmit = page.locator('form[role="search"] button[type="submit"]');
    this.answerBlock = page.getByTestId("search-answer");
    this.sourceList = page.getByTestId("search-source-list");
    this.sourceCards = page.getByTestId("search-source-card");
    this.errorBox = page.getByTestId("search-error-box");
    this.retryButton = page.getByTestId("search-retry");
    this.resultsHeader = page.locator('[data-testid="search-results-header"]');
    this.emptyState = page.getByTestId("search-empty-state");
    this.loadingState = page.locator('[role="status"]');
    this.resultCards = page.getByTestId("search-source-card");
  }

  async goto(query?: string): Promise<void> {
    const url = query ? `/search?q=${encodeURIComponent(query)}` : "/search";
    await this.page.goto(url);
  }
}
