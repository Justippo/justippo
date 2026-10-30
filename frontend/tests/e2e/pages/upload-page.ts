import type { Page, Locator } from "@playwright/test";
import { expect } from "@playwright/test";

export class UploadPage {
  readonly page: Page;
  readonly dropZone: Locator;
  readonly fileInput: Locator;
  readonly langSelect: Locator;
  readonly submitBtn: Locator;
  readonly cancelBtn: Locator;
  readonly errorText: Locator;
  readonly statusUploading: Locator;
  readonly statusTranslating: Locator;
  readonly successHeading: Locator;
  readonly pagesTable: Locator;
  readonly uploadAnotherBtn: Locator;
  readonly continueBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.dropZone = page.getByTestId("upload-dropzone");
    this.fileInput = page.locator('input[type="file"]');
    this.langSelect = page.getByTestId("translation-lang-select");
    this.submitBtn = page.locator('button:has-text("Upload for analysis")');
    this.cancelBtn = page.locator('button:has-text("Cancel")');
    this.errorText = page.getByTestId("upload-error");
    this.statusUploading = page.locator("text=Uploading and extracting text");
    this.statusTranslating = page.locator("text=Translating to DE");
    this.successHeading = page.locator("text=Document processed");
    this.pagesTable = page.locator("table");
    this.uploadAnotherBtn = page.locator('button:has-text("Upload Another")');
    this.continueBtn = page.getByRole("button", { name: "Continue to translation" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/translation?start=upload");
  }

  async uploadFile(fileName: string): Promise<void> {
    const fileInput = this.page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: fileName,
      mimeType: "application/pdf",
      buffer: Buffer.from("mock pdf content"),
    });
  }

  async selectLanguage(lang: string): Promise<void> {
    await this.langSelect.selectOption(lang);
  }

  async submit(): Promise<void> {
    await this.submitBtn.click();
  }

  async cancel(): Promise<void> {
    await this.cancelBtn.click();
  }

  async waitForUploading(): Promise<void> {
    await expect(this.statusUploading).toBeVisible({ timeout: 15_000 });
  }

  async waitForTranslating(): Promise<void> {
    await expect(this.statusTranslating).toBeVisible({ timeout: 15_000 });
  }

  async waitForSuccess(): Promise<void> {
    await expect(this.successHeading).toBeVisible({ timeout: 30_000 });
  }
}
