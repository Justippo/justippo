import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useUploadState } from "./useUploadState";

vi.mock("@/lib/api-generated", () => ({
  uploadDocument: vi.fn(),
}));

import { uploadDocument } from "@/lib/api-generated";
const mockUpload = vi.mocked(uploadDocument);

describe("useUploadState", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it("starts in empty state", () => {
    const { result } = renderHook(() => useUploadState());
    expect(result.current.status).toBe("empty");
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("transitions to loading then success", async () => {
    const mockResult = {
      doc_id: "doc-1",
      status: "processed",
      ephemeral: true,
      page_count: 1,
      target_language: "de" as const,
      pages: [{ page: 1, text: "hello", confidence: 0.95 }],
      classification: {
        document_type: "contract",
        language_code: "en",
        quality_score: 0.9,
        confidence: 0.95,
      },
    };
    mockUpload.mockResolvedValue(mockResult);

    const { result } = renderHook(() => useUploadState());
    const file = new File(["content"], "test.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });
    expect(result.current.status).toBe("loading");

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.result).toEqual(mockResult);
  });

  it("transitions to error on failure", async () => {
    mockUpload.mockRejectedValue(new Error("Upload failed (413): too large"));

    const { result } = renderHook(() => useUploadState());
    const file = new File(["x"], "big.pdf");

    act(() => {
      result.current.upload(file, "de");
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toContain("Upload failed");
  });

  it("normalizes an unknown OCR language before translation", async () => {
    mockUpload.mockResolvedValue({
      doc_id: "doc-und",
      status: "processed",
      ephemeral: true,
      page_count: 1,
      target_language: "de",
      pages: [{ page: 1, text: "Detected text", confidence: 0.8 }],
      classification: {
        document_type: "unknown",
        language_code: "und",
        quality_score: 0.8,
        confidence: 0.8,
      },
    });

    const { result } = renderHook(() => useUploadState());
    const file = new File(["content"], "unknown.png", { type: "image/png" });

    act(() => {
      result.current.upload(file, "de");
    });
    await waitFor(() => expect(result.current.status).toBe("success"));

    const documentWrite = window.sessionStorage.getItem("evidence-eu-document-data");
    expect(documentWrite).toBeDefined();
    expect(JSON.parse(documentWrite ?? "{}").sourceLang).toBe("en");
    expect(JSON.parse(documentWrite ?? "{}").targetLang).toBe("de");
  });

  it("reset returns to empty", async () => {
    mockUpload.mockResolvedValue({
      doc_id: "x",
      status: "processed",
      ephemeral: true,
      page_count: 0,
      target_language: "de",
      pages: [],
      classification: { document_type: "x", language_code: "x", quality_score: 0, confidence: 0 },
    });
    const { result } = renderHook(() => useUploadState());
    const file = new File(["x"], "x.pdf");
    act(() => {
      result.current.upload(file, "en");
    });
    await waitFor(() => expect(result.current.status).toBe("success"));
    act(() => {
      result.current.reset();
    });
    expect(result.current.status).toBe("empty");
  });
});
