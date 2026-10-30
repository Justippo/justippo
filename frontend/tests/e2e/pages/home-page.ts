import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page Object: Home page (/)
 */
export class HomePage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly searchSubmit: Locator;
  readonly exampleQueries: Locator;
  readonly headline: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.locator("#home-search-input");
    this.searchSubmit = page.locator("#home-search-submit");
    this.exampleQueries = page.locator('[data-testid="example-query"]');
    this.headline = page.locator("#hp-headline");
  }

  async goto(): Promise<void> {
    await this.page.goto("/");
  }

  async search(query: string): Promise<void> {
    // Use pressSequentially() instead of fill() because WebKit does not
    // reliably fire React's onChange synthetic event on fill(), causing
    // the submit button's disabled={!query.trim()} to remain true
    // indefinitely. pressSequentially() types character-by-character
    // through the keyboard API, which fires all events on all browsers.
    await this.searchInput.pressSequentially(query);
    // Wait for React to re-render and remove the `disabled` attribute.
    await this.page.locator("#home-search-submit:not([disabled])").waitFor({ timeout: 10_000 });
    await this.searchSubmit.click();
  }
}
