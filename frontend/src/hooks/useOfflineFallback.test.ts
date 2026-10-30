import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockUseSearchSSE = vi.fn(() => ({
  results: [],
  status: "empty",
  error: null,
  retry: vi.fn(),
  search: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("./useSearchSSE", () => ({
  useSearchSSE: () => mockUseSearchSSE(),
}));

const mockUseUploadState = vi.fn(() => ({
  status: "empty",
  result: null,
  error: null,
  upload: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("./useUploadState", () => ({
  useUploadState: () => mockUseUploadState(),
}));

const mockUseTranslationState = vi.fn(() => ({
  status: "empty",
  result: null,
  error: null,
  isTruncated: false,
  translate: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("./useTranslationState", () => ({
  useTranslationState: () => mockUseTranslationState(),
}));

const mockUseOfflineMode = vi.fn();
vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

import { useSearch } from "./useSearch";
import { useUpload } from "./useUpload";
import { useTranslate } from "./useTranslate";

const FULL_FALLBACK = {
  fallbackMode: true,
  upload: {
    doc_id: "demo-001",
    status: "processed",
    ephemeral: true,
    page_count: 1,
    target_language: "de",
    pages: [{ page: 1, text: "Permit form", confidence: 0.94 }],
    classification: {
      document_type: "residence_permit",
      language_code: "en",
      quality_score: 0.94,
      confidence: 0.94,
    },
  },
  translate: {
    job_id: "demo-job-001",
    status: "done",
    translated_pages: [{ page: 1, text: "Permit form translated" }],
    error: null,
  },
  search: [
    {
      id: "chunk-demo-001",
      text: "Residence permit extension guidance",
      type: "world",
      chunk_id: "chunk-demo-001",
      entities: ["Aufenthaltstitel"],
      rank: 1,
    },
  ],
} as const;

describe("offline fallback wiring", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockUseOfflineMode.mockReturnValue({
      status: "offline",
      isOfflineMode: true,
      fallbackData: FULL_FALLBACK,
      retry: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("useSearch returns fallback results in offline mode", () => {
    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.search("residence permit");
    });

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.results).toEqual(FULL_FALLBACK.search);
  });

  it("useUpload returns fallback upload in offline mode", () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(["content"], "permit.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(FULL_FALLBACK.upload);
  });

  it("useTranslate returns fallback translation in offline mode", () => {
    const { result } = renderHook(() => useTranslate());

    act(() => {
      result.current.translate("demo-001", "en", "de", [{ page: 1, text: "Permit form" }]);
    });

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(FULL_FALLBACK.translate);
  });
});
