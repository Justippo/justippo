import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useTranslationState } from "./useTranslationState";
import { TRANSLATION_ERROR_COPY } from "@/data/mockData";

vi.mock("@/lib/api-generated", () => ({
  translateDocument: vi.fn(),
}));

import { translateDocument } from "@/lib/api-generated";
const mockTranslate = vi.mocked(translateDocument);

describe("useTranslationState", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("starts in empty state", () => {
    const { result } = renderHook(() => useTranslationState());
    expect(result.current.status).toBe("empty");
  });

  it("transitions to success with translated pages", async () => {
    mockTranslate.mockResolvedValue({
      job_id: "j1",
      status: "done",
      translated_pages: [{ page: 1, text: "Hallo Welt" }],
    });
    const { result } = renderHook(() => useTranslationState());
    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello World" }]);
    });
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.result?.translated_pages?.[0].text).toBe("Hallo Welt");
    expect(result.current.isTruncated).toBe(false);
  });

  it("requests a refreshed explanation using the selected target language", async () => {
    mockTranslate.mockResolvedValue({
      job_id: "j-explanation",
      status: "done",
      translated_pages: [],
    });
    const { result } = renderHook(() => useTranslationState());

    act(() => {
      result.current.translate("doc-1", "de", "fr", [{ page: 1, text: "Aufenthaltstitel" }], {
        classification: { document_type: "residence_permit", language_code: "de" },
        includeDocumentExplanation: true,
      });
    });

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(mockTranslate).toHaveBeenCalledWith(
      expect.objectContaining({
        target_language: "fr",
        classification: {
          document_type: "residence_permit",
          language_code: "de",
        },
        include_document_explanation: true,
      }),
      undefined,
      expect.any(AbortSignal)
    );
  });

  it("treats a partial response as a usable success", async () => {
    mockTranslate.mockResolvedValue({
      job_id: "j-partial",
      status: "partial",
      translated_pages: [],
    });
    const { result } = renderHook(() => useTranslationState());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello" }]);
    });

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.result?.status).toBe("partial");
  });

  it("treats an all-sections-failed response as an error", async () => {
    mockTranslate.mockResolvedValue({
      job_id: "j-failed",
      status: "failed",
      translated_pages: [],
      error: "Translation could not be completed.",
    });
    const { result } = renderHook(() => useTranslationState());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello" }]);
    });

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Translation could not be completed.");
  });

  it("detects truncation suffix", async () => {
    mockTranslate.mockResolvedValue({
      job_id: "j2",
      status: "done",
      translated_pages: [{ page: 1, text: "Text hier[truncated]" }],
    });
    const { result } = renderHook(() => useTranslationState());
    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Long text" }]);
    });
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.isTruncated).toBe(true);
  });

  it("transitions to error on failure", async () => {
    mockTranslate.mockRejectedValue(new Error("Translation failed (500)"));
    const { result } = renderHook(() => useTranslationState());
    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "x" }]);
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toContain("Translation failed");
  });

  it("times out a stalled translation and exposes a recoverable error", async () => {
    vi.useFakeTimers();
    mockTranslate.mockImplementation(
      (_request, _headers, signal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        })
    );
    const { result } = renderHook(() => useTranslationState());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello World" }]);
    });
    expect(result.current.status).toBe("loading");

    await act(async () => {
      vi.advanceTimersByTime(30_000);
      await Promise.resolve();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(TRANSLATION_ERROR_COPY.timeout);
  });

  it("cancels a superseded translation request", () => {
    const signals: AbortSignal[] = [];
    mockTranslate.mockImplementation((_request, _headers, signal) => {
      if (signal) signals.push(signal);
      return new Promise(() => undefined);
    });
    const { result } = renderHook(() => useTranslationState());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello" }]);
      result.current.translate("doc-1", "en", "fr", [{ page: 1, text: "Hello" }]);
    });

    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });
});
