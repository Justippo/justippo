import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PDF_REFERENCE_SAMPLE_RESULT } from "@/data/mockData";
import { usePdfReferenceTranslation } from "./usePdfReferenceTranslation";

vi.mock("@/lib/api-generated", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-generated")>("@/lib/api-generated");
  return { ...actual, translatePdfReference: vi.fn() };
});

import { PdfReferenceApiError, translatePdfReference } from "@/lib/api-generated";

const mockTranslate = vi.mocked(translatePdfReference);
const file = new File(["%PDF-1.7"], "form.pdf", { type: "application/pdf" });

describe("usePdfReferenceTranslation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((value: Blob) => (value === file ? "blob:source" : "blob:translated")),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("returns PDF URLs and grounded results after translation", async () => {
    mockTranslate.mockResolvedValue(PDF_REFERENCE_SAMPLE_RESULT);
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "en", 2);
    });
    await waitFor(() => expect(result.current.status).toBe("success"));

    expect(result.current.sourcePdfUrl).toBe("blob:source");
    expect(result.current.translatedPdfUrl).toBe("blob:translated");
    expect(result.current.result?.document_explanation.requirements).toHaveLength(2);
    expect(result.current.warningMessages[0]).toContain("reference copy");
  });

  it("maps provider errors to actionable product copy", async () => {
    mockTranslate.mockRejectedValue(
      new PdfReferenceApiError("PASSWORD_REQUIRED", "provider detail that should not be displayed")
    );
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "en", 2);
    });
    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.error).toContain("password-protected");
    expect(result.current.error).not.toContain("provider detail");
  });

  it("turns a malformed translated PDF into a recoverable error", async () => {
    mockTranslate.mockResolvedValue({
      ...PDF_REFERENCE_SAMPLE_RESULT,
      translated_pdf_b64: "not valid base64!",
    });
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "en", 2);
    });
    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.error).toBe(
      "PDF reference translation could not be completed. Please try again."
    );
    expect(result.current.result).toBeNull();
    expect(result.current.translatedPdfUrl).toBeNull();
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("cancels a superseded request", () => {
    const signals: AbortSignal[] = [];
    mockTranslate.mockImplementation((_file, _source, _target, _pages, _headers, signal) => {
      if (signal) signals.push(signal);
      return new Promise(() => undefined);
    });
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "en", 2);
      result.current.translate(file, "de", "fr", 2);
    });

    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("replaces the translated artifact when the target changes on the same screen", async () => {
    mockTranslate
      .mockResolvedValueOnce({
        ...PDF_REFERENCE_SAMPLE_RESULT,
        request_id: "request-en",
        target_language: "en",
      })
      .mockResolvedValueOnce({
        ...PDF_REFERENCE_SAMPLE_RESULT,
        request_id: "request-fr",
        target_language: "fr",
      });
    let translatedUrlCount = 0;
    vi.mocked(URL.createObjectURL).mockImplementation((value: Blob | MediaSource) => {
      if (value === file) return "blob:source";
      translatedUrlCount += 1;
      return `blob:translated-${translatedUrlCount}`;
    });
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "en", 2);
    });
    await waitFor(() => expect(result.current.translatedPdfUrl).toBe("blob:translated-1"));

    act(() => {
      result.current.translate(file, "de", "fr", 2);
    });
    expect(result.current.status).toBe("loading");
    expect(result.current.result).toBeNull();
    await waitFor(() => expect(result.current.translatedPdfUrl).toBe("blob:translated-2"));

    expect(result.current.result?.target_language).toBe("fr");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:translated-1");
    expect(mockTranslate).toHaveBeenLastCalledWith(
      file,
      "de",
      "fr",
      2,
      undefined,
      expect.any(AbortSignal)
    );
  });

  it("rejects a response for a different target language", async () => {
    mockTranslate.mockResolvedValue({
      ...PDF_REFERENCE_SAMPLE_RESULT,
      target_language: "en",
    });
    const { result } = renderHook(() => usePdfReferenceTranslation(file));

    act(() => {
      result.current.translate(file, "de", "fr", 2);
    });
    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.result).toBeNull();
    expect(result.current.error).toContain("readability and language checks");
  });
});
