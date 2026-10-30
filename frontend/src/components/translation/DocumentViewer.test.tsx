import { fireEvent, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DocumentViewer } from "./DocumentViewer";
import { TRANSLATION_SAMPLE_RESULT, TRANSLATION_SAMPLE_SOURCE_PAGES } from "@/data/mockData";
import { TARGET_LANGUAGE_OPTIONS } from "@/lib/language-codes";
import { renderWithI18n as render } from "@/test-utils";

describe("DocumentViewer", () => {
  it("renders empty state with upload CTA", () => {
    render(
      <DocumentViewer
        viewState="empty"
        filename="Document"
        sourceLang="en"
        targetLang="de"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[]}
        sourceSections={[]}
        result={null}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Start translation" })).toBeDefined();
    expect(
      screen.getByText("No document loaded. Start a translation to select and process a document.")
    ).toBeDefined();
  });

  it("renders success state with language pair badge and comparison panels", () => {
    render(
      <DocumentViewer
        viewState="success"
        filename="residence-permit-application.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="compare"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={TRANSLATION_SAMPLE_SOURCE_PAGES}
        sourceSections={[]}
        result={TRANSLATION_SAMPLE_RESULT}
        isTruncated
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );
    expect(screen.getByTestId("language-pair-badge")).toBeDefined();
    expect(screen.getByTestId("language-pair-source").textContent).toBe("DE");
    expect(screen.getByTestId("language-pair-target").textContent).toBe("EN");
    expect(screen.getByTestId("truncated-banner")).toBeDefined();
    expect(screen.getByTestId("viewer-panel-original-text-1-0")).toBeDefined();
    expect(screen.getByTestId("viewer-panel-translated-text-1-0")).toBeDefined();
    expect(screen.getByTestId("translate-another")).toBeDefined();
  });

  it("calls onUploadClick when translate another button is clicked", () => {
    const onUploadClick = vi.fn();
    render(
      <DocumentViewer
        viewState="success"
        filename="document.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={TRANSLATION_SAMPLE_SOURCE_PAGES}
        sourceSections={[]}
        result={TRANSLATION_SAMPLE_RESULT}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={onUploadClick}
      />
    );
    fireEvent.click(screen.getByTestId("translate-another"));
    expect(onUploadClick).toHaveBeenCalledOnce();
  });

  it("labels extracted-text PDF understanding without claiming preserved layout", () => {
    render(
      <DocumentViewer
        viewState="success"
        filename="fillable-form.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[{ page: 1, text: "Wohnsitznachweis beifügen" }]}
        sourceSections={[]}
        result={{
          job_id: "job-understanding",
          status: "done",
          translated_pages: [{ page: 1, text: "Attach proof of residence" }],
        }}
        isTruncated={false}
        isDocumentUnderstanding
        documentExplanation={{
          document_type: "residence_application",
          language: "en",
          requirements: [
            { text: "Wohnsitznachweis beifügen", kind: "instruction", page_number: 1 },
          ],
          legal_context_status: "not_found",
          citations: [],
          warnings: ["NO_VERIFIED_EU_LAW_SOURCE"],
        }}
        documentExplanationWarnings={["No verified EU-law source was found for this document."]}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );

    expect(screen.getByText("Document understanding translation")).toBeDefined();
    expect(
      screen.getByText(/does not reproduce the PDF layout or fillable controls/)
    ).toBeDefined();
    expect(screen.getByText("What this document asks for")).toBeDefined();
    expect(screen.getByText("Related EU-law context")).toBeDefined();
  });

  it("defaults to a focused translated-document result mode", () => {
    const onShowComparison = vi.fn();
    const onDownload = vi.fn();
    render(
      <DocumentViewer
        viewState="success"
        filename="residence-permit-application.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={TRANSLATION_SAMPLE_SOURCE_PAGES}
        sourceSections={[]}
        result={TRANSLATION_SAMPLE_RESULT}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={onShowComparison}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
        canDownload
        onDownload={onDownload}
      />
    );

    expect(screen.queryByTestId("viewer-panel-original")).toBeNull();
    expect(screen.getAllByTestId("viewer-panel-translated")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Translation" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(onShowComparison).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Download text" }));
    expect(onDownload).toHaveBeenCalledOnce();
  });

  it("renders error state with retry action", () => {
    render(
      <DocumentViewer
        viewState="error"
        filename="Document"
        sourceLang="en"
        targetLang="de"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[]}
        sourceSections={[]}
        result={null}
        isTruncated={false}
        error="Translation could not be completed."
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );
    expect(screen.getByTestId("viewer-error").textContent).toContain(
      "Translation could not be completed."
    );
    expect(screen.getByText("Try again")).toBeDefined();
    expect(screen.getByTestId("translate-another")).toBeDefined();
  });

  it("renders loading skeleton", () => {
    render(
      <DocumentViewer
        viewState="loading"
        filename="Document"
        sourceLang="en"
        targetLang="de"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[{ page: 1, text: "Source section" }]}
        sourceSections={[{ page: 1, index: 0, text: "Source section" }]}
        result={null}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Translating document")).toBeDefined();
    expect(screen.getByText("Source section")).toBeDefined();
    expect(screen.getByLabelText("Translation pending")).toBeDefined();
    expect(screen.getByTestId("translate-another")).toBeDefined();
  });

  it("renders aligned structured translation sections", () => {
    render(
      <DocumentViewer
        viewState="success"
        filename="form.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="compare"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[{ page: 1, text: "Abschnitt eins\n\nAbschnitt zwei" }]}
        sourceSections={[]}
        result={{
          job_id: "job-sections",
          status: "done",
          translated_pages: [
            {
              page: 1,
              text: "Section one\n\nSection two",
              sections: [
                { index: 0, source_text: "Abschnitt eins", translated_text: "Section one" },
                { index: 1, source_text: "Abschnitt zwei", translated_text: "Section two" },
              ],
            },
          ],
        }}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );

    expect(screen.getByText("Abschnitt eins")).toBeDefined();
    expect(screen.getByText("Section one")).toBeDefined();
    expect(screen.getByText("Abschnitt zwei")).toBeDefined();
    expect(screen.getByText("Section two")).toBeDefined();
    expect(screen.getAllByText("Section 1 — German")).toHaveLength(1);
    expect(screen.getAllByText("Section 1 — English")).toHaveLength(1);
    expect(screen.queryByText(/Page 1, section/)).toBeNull();
  });

  it("does not restore source page furniture when the backend returns no sections", () => {
    render(
      <DocumentViewer
        viewState="success"
        filename="form.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="compare"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[{ page: 1, text: "| --- | --- |" }]}
        sourceSections={[]}
        result={{
          job_id: "job-structure-only",
          status: "done",
          translated_pages: [{ page: 1, text: "", sections: [] }],
        }}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );

    expect(screen.queryByText("| --- | --- |")).toBeNull();
    expect(screen.queryByText(/Page 1, section/)).toBeNull();
  });

  it("keeps successful sections visible and marks failed sections for review", () => {
    render(
      <DocumentViewer
        viewState="success"
        filename="form.pdf"
        sourceLang="de"
        targetLang="en"
        resultMode="translation"
        languageOptions={TARGET_LANGUAGE_OPTIONS}
        sourcePages={[{ page: 1, text: "Abschnitt eins\n\nAbschnitt zwei" }]}
        sourceSections={[]}
        result={{
          job_id: "job-partial",
          status: "partial",
          translated_pages: [
            {
              page: 1,
              text: "Section one",
              status: "partial",
              sections: [
                {
                  index: 0,
                  source_text: "Abschnitt eins",
                  translated_text: "Section one",
                  status: "translated",
                  attempts: 1,
                },
                {
                  index: 1,
                  source_text: "Abschnitt zwei",
                  translated_text: "",
                  status: "failed",
                  attempts: 2,
                  error_code: "TRANSLATION_SECTION_FAILED",
                },
              ],
            },
          ],
          quality_report: {
            status: "review",
            terminology_review_status: "applied",
            source_section_count: 2,
            translated_section_count: 1,
            failed_section_count: 1,
            checks: [
              {
                code: "SECTION_COVERAGE",
                status: "warning",
                message: "1 of 2 sections require review.",
              },
            ],
          },
          glossary_terms_applied: 1,
        }}
        isTruncated={false}
        error={null}
        onLanguageChange={vi.fn()}
        onShowTranslation={vi.fn()}
        onShowComparison={vi.fn()}
        onReset={vi.fn()}
        onUploadClick={vi.fn()}
      />
    );

    expect(screen.getByTestId("partial-translation-banner")).toBeDefined();
    expect(screen.getByText("Section one")).toBeDefined();
    expect(
      screen.getByText("Translation unavailable for this section after 2 attempts.")
    ).toBeDefined();
    expect(screen.getByTestId("translation-quality-report")).toBeDefined();
    expect(screen.getByText(/Terminology review: 1 glossary correction applied/)).toBeDefined();
  });
});
