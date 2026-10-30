import { Page, Locator } from "@playwright/test";

export class LoginPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitBtn: Locator;
  readonly matrixSubmitBtn: Locator;
  readonly formError: Locator;
  readonly loadingState: Locator;

  readonly navLoginBtn: Locator;
  readonly navLogoutBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Welcome back" });
    this.emailInput = page.getByTestId("login-email");
    this.passwordInput = page.getByTestId("login-password");
    this.submitBtn = page.getByTestId("login-submit");
    this.matrixSubmitBtn = page.getByTestId("matrix-login-submit");
    this.formError = page.getByRole("alert");
    this.loadingState = page.getByLabel("Signing in");

    this.navLoginBtn = page.getByTestId("nav-btn-login");
    this.navLogoutBtn = page.getByTestId("nav-btn-logout");
  }

  async goto() {
    await this.page.goto("/login");
    await this.heading.waitFor({ state: "visible", timeout: 15_000 });
  }

  async fillForm(email: string, password: string) {
    // Only applicable when email/password fields are visible (non-Matrix mode)
    const emailVisible = await this.emailInput.isVisible().catch(() => false);
    if (emailVisible) {
      await this.emailInput.fill(email);
      await this.passwordInput.fill(password);
    }
  }

  async submit() {
    // In Matrix auth mode, click the "Continue securely" button.
    // In legacy mode, click the regular submit button.
    const matrixVisible = await this.matrixSubmitBtn.isVisible().catch(() => false);
    if (matrixVisible) {
      await this.matrixSubmitBtn.click();
    } else {
      await this.submitBtn.click();
    }
  }

  async openFromNav() {
    await this.navLoginBtn.click();
    await this.heading.waitFor({ state: "visible", timeout: 15_000 });
  }

  async logoutFromNav() {
    await this.navLogoutBtn.click();
    await this.page
      .waitForFunction(() => window.localStorage.getItem("evidenceeu_auth") === null, undefined, {
        timeout: 15_000,
      })
      .catch(() => {
        // In Matrix mode, localStorage may not be used — check URL instead
      });
    await this.page.waitForURL(/\/login(?:\?|$)/, { timeout: 15_000 });
    await this.heading.waitFor({ state: "visible", timeout: 15_000 });
  }
}
