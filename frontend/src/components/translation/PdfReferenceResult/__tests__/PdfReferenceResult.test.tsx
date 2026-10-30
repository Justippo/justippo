import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PDF_REFERENCE_SAMPLE_RESULT } from "@/data/mockData";
import { TARGET_LANGUAGE_OPTIONS } from "@/lib/language-codes";
import { PdfReferenceResult } from "../PdfReferenceResult";
import { renderWithProviders as render } from "@/test-utils";

const handlers = {
  onLanguageChange: vi.fn(),
  onShowTranslation: vi.fn(),
  onShowComparison: vi.fn(),
  onReset: vi.fn(),
  onUploadClick: vi.fn(),
};

const baseProps = {
  filename: "residence-application.pdf",
  sourceLang: "de",
  targetLang: "en",
  resultMode: "translation" as const,
  languageOptions: TARGET_LANGUAGE_OPTIONS,
  result: PDF_REFERENCE_SAMPLE_RESULT,
  sourcePdfUrl: "blob:source",
  translatedPdfUrl: "blob:translated",
  warnings: ["This translated PDF is a reference copy, not an official replacement."],
  error: null,
  ...handlers,
};

describe("PdfReferenceResult", () => {
  it("renders the reference artifact, requirements, and official citations", () => {
    render(<PdfReferenceResult {...baseProps} viewState="success" />);

    expect(screen.getByText("Reference copy only")).toBeDefined();
    expect(screen.getByTitle(/Translated PDF reference/)).toHaveAttribute("src", "blob:translated");
    expect(screen.getByText("Proof of residence")).toBeDefined();
    expect(screen.getByRole("link", { name: /Directive 2004\/38\/EC/ })).toHaveAttribute(
      "href",
      expect.stringContaining("eur-lex.europa.eu")
    );
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "download",
      "translated-residence-application.pdf"
    );
    expect(screen.getByTestId("translate-another")).toBeDefined();
  });

  it("calls onUploadClick when translate another button is clicked", () => {
    render(<PdfReferenceResult {...baseProps} viewState="success" />);
    fireEvent.click(screen.getByTestId("translate-another"));
    expect(handlers.onUploadClick).toHaveBeenCalled();
  });

  it("shows the original only in comparison mode", () => {
    const onShowComparison = vi.fn();
    const { rerender } = render(
      <PdfReferenceResult {...baseProps} viewState="success" onShowComparison={onShowComparison} />
    );
    expect(screen.queryByTitle(/Original PDF/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(onShowComparison).toHaveBeenCalledOnce();

    rerender(<PdfReferenceResult {...baseProps} viewState="success" resultMode="compare" />);
    expect(screen.getByTitle(/Original PDF/)).toHaveAttribute("src", "blob:source");
  });

  it("renders loading, error, and empty states with next actions", () => {
    const { rerender } = render(
      <PdfReferenceResult {...baseProps} viewState="loading" result={null} />
    );
    expect(screen.getByRole("status")).toBeDefined();
    expect(screen.getByText("Translating DE → EN")).toBeDefined();
    expect(screen.getByLabelText("Target language")).toBeDisabled();

    rerender(
      <PdfReferenceResult
        {...baseProps}
        viewState="error"
        result={null}
        error="Translation unavailable"
      />
    );
    expect(screen.getByTestId("pdf-reference-error")).toHaveTextContent("Translation unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(handlers.onReset).toHaveBeenCalled();

    rerender(<PdfReferenceResult {...baseProps} viewState="empty" result={null} />);
    expect(screen.getByRole("button", { name: "Choose a PDF" })).toBeDefined();
  });
});
