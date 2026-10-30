import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTranslationWorkflow } from "./useTranslationWorkflow";

const { mockReplace } = vi.hoisted(() => ({ mockReplace: vi.fn() }));

const { mockPathname } = vi.hoisted(() => ({ mockPathname: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => mockPathname(),
}));

const DOCUMENT_SESSION = {
  filename: "permit.pdf",
  sourcePages: [{ page: 1, text: "Extracted text" }],
  documentId: "doc-1",
  sourceLang: "en",
  targetLang: "de",
};

describe("useTranslationWorkflow", () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPathname.mockReset();
    mockPathname.mockReturnValue("/translation");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/translation");
  });

  it("starts with upload when no processed document exists", async () => {
    const { result } = renderHook(() => useTranslationWorkflow());

    await waitFor(() => expect(result.current.stage).toBe("upload"));
  });

  it("always starts at upload on mount regardless of saved session", async () => {
    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    const { result } = renderHook(() => useTranslationWorkflow());

    await waitFor(() => expect(result.current.stage).toBe("upload"));
    expect(sessionStorage.getItem("evidence-eu-document-data")).toBeNull();
  });

  it("forces a fresh upload flow for a legacy upload entry", async () => {
    window.history.replaceState(null, "", "/translation?start=upload");
    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    const { result } = renderHook(() => useTranslationWorkflow());

    await waitFor(() => expect(result.current.stage).toBe("upload"));
  });

  it("requires the original PDF again after a page reload", async () => {
    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({ ...DOCUMENT_SESSION, pdfReferenceEligible: true })
    );
    const { result } = renderHook(() => useTranslationWorkflow());

    await waitFor(() => expect(result.current.stage).toBe("upload"));
  });

  it("preserves the contextual comparison intent", async () => {
    window.history.replaceState(null, "", "/translation?view=compare");
    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    const { result } = renderHook(() => useTranslationWorkflow());

    await waitFor(() => expect(result.current.stage).toBe("translate"));
    expect(result.current.resultMode).toBe("compare");
  });

  it("reacts when client-side navigation requests a fresh upload", async () => {
    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    const { result, rerender } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    window.history.pushState(null, "", "/translation?start=upload");
    rerender();

    await waitFor(() => expect(result.current.stage).toBe("upload"));
  });

  it("persists the selected language before continuing", async () => {
    const { result } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    act(() => result.current.onContinue("fr", null));

    const stored = JSON.parse(
      sessionStorage.getItem("evidence-eu-document-data") ?? "{}"
    ) as typeof DOCUMENT_SESSION;
    expect(stored.targetLang).toBe("fr");
    expect(result.current.stage).toBe("translate");
  });

  it("keeps the original PDF in memory for the composed workflow", async () => {
    const { result } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({
        ...DOCUMENT_SESSION,
        pdfReferenceEligible: false,
        pdfProcessingMode: "pdf_reference_translation",
      })
    );
    const file = new File(["%PDF-1.7"], "permit.pdf", { type: "application/pdf" });

    act(() => result.current.onContinue("fr", file));

    expect(result.current.referenceFile).toBe(file);
  });

  it("uses extracted pages when PDF layout rendering is unavailable", async () => {
    const { result } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({
        ...DOCUMENT_SESSION,
        pdfReferenceEligible: false,
        pdfProcessingMode: "document_understanding_translation",
      })
    );
    const file = new File(["%PDF-1.7"], "permit.pdf", { type: "application/pdf" });

    act(() => result.current.onContinue("fr", file));

    expect(result.current.referenceFile).toBeNull();
  });

  it("returns directly to upload when choosing another PDF from the same URL", async () => {
    window.history.replaceState(null, "", "/translation?start=upload");
    const { result } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    sessionStorage.setItem(
      "evidence-eu-document-data",
      JSON.stringify({
        ...DOCUMENT_SESSION,
        pdfReferenceEligible: true,
        pdfProcessingMode: "pdf_reference_translation",
      })
    );
    const file = new File(["%PDF-1.7"], "permit.pdf", { type: "application/pdf" });

    act(() => result.current.onContinue("fr", file));
    expect(result.current.stage).toBe("translate");
    expect(result.current.referenceFile).toBe(file);

    // onContinue now also calls router.replace to reflect documentId in the
    // URL — clear it so the assertion below is scoped to onChooseAnother.
    mockReplace.mockClear();
    act(() => result.current.onChooseAnother());

    expect(result.current.stage).toBe("upload");
    expect(result.current.referenceFile).toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("normalizes the URL when choosing another PDF from a translated session", async () => {
    const { result } = renderHook(() => useTranslationWorkflow());
    await waitFor(() => expect(result.current.stage).toBe("upload"));

    sessionStorage.setItem("evidence-eu-document-data", JSON.stringify(DOCUMENT_SESSION));
    act(() => result.current.onContinue("de", null));
    await waitFor(() => expect(result.current.stage).toBe("translate"));

    act(() => result.current.onChooseAnother());

    expect(result.current.stage).toBe("upload");
    expect(mockReplace).toHaveBeenCalledWith("/translation?start=upload");
  });
});
