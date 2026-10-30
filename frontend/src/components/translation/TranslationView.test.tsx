import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, it, expect } from "vitest";
import { TranslationView } from "./TranslationView";
import { renderWithI18n as render } from "@/test-utils";

describe("TranslationView", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("starts the unified upload and OCR flow when no document exists", async () => {
    render(<TranslationView />);
    expect(await screen.findByRole("heading", { name: "Translate document" })).toBeDefined();
    expect(screen.getByText(/OCR extraction and translation/)).toBeDefined();
  });

  it("renders empty state with upload CTA", () => {
    render(<TranslationView forcedState="empty" />);
    expect(screen.getByTestId("viewer-upload-cta")).toBeDefined();
  });

  it("renders success state with language pair badge", () => {
    render(<TranslationView forcedState="success" />);
    expect(screen.getByTestId("language-pair-badge")).toBeDefined();
    expect(screen.getByTestId("viewer-filename").textContent).toContain("residence-permit");
    expect(screen.queryByTestId("viewer-panel-original")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(screen.getAllByTestId("viewer-panel-original")).toHaveLength(3);
  });

  it("renders error state", () => {
    render(<TranslationView forcedState="error" />);
    expect(screen.getByTestId("viewer-error")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<TranslationView forcedState="loading" />);
    expect(screen.getByLabelText("Translating document")).toBeDefined();
  });
});
