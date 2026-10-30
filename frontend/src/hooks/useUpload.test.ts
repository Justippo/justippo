import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockUseUploadState = vi.fn();
vi.mock("./useUploadState", () => ({
  useUploadState: () => mockUseUploadState(),
}));

const mockUseOfflineMode = vi.fn();
vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

import { useUpload } from "./useUpload";
import { UPLOAD_ERROR_COPY } from "@/data/mockData";

const FALLBACK_UPLOAD = {
  doc_id: "demo-001",
  status: "processed",
  ephemeral: true,
  page_count: 1,
  target_language: "de",
  pages: [
    {
      page: 1,
      text: "EU Residence Permit Application Form",
      confidence: 0.94,
    },
  ],
  classification: {
    document_type: "residence_permit",
    language_code: "en",
    quality_score: 0.94,
    confidence: 0.94,
  },
} as const;

function mockLive(overrides: Partial<ReturnType<typeof mockUseUploadState>> = {}) {
  const liveUpload = vi.fn();
  const liveReset = vi.fn();
  mockUseUploadState.mockReturnValue({
    status: "empty",
    result: null,
    error: null,
    upload: liveUpload,
    reset: liveReset,
    ...overrides,
  });
  return { liveUpload, liveReset };
}

describe("useUpload", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: false,
      fallbackData: null,
      status: "healthy",
      retry: vi.fn(),
    });
    mockLive();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts in empty state via live upload", () => {
    const { result } = renderHook(() => useUpload());
    expect(result.current.status).toBe("empty");
    expect(result.current.result).toBeNull();
  });

  it("delegates upload to live API when healthy", () => {
    const { liveUpload } = mockLive();
    const { result } = renderHook(() => useUpload());
    const file = new File(["content"], "contract.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });

    expect(liveUpload).toHaveBeenCalledWith(file, "de");
  });

  it("preserves an active live upload when health enters fallback mode", () => {
    const liveResult = { ...FALLBACK_UPLOAD, doc_id: "live-001" };
    const { liveUpload } = mockLive();
    const { result, rerender } = renderHook(() => useUpload());
    const file = new File(["content"], "contract.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });
    expect(liveUpload).toHaveBeenCalledWith(file, "de");

    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, upload: FALLBACK_UPLOAD },
      status: "offline",
      retry: vi.fn(),
    });
    mockLive({ status: "success", result: liveResult });
    rerender();

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(liveResult);
  });

  it("serves demo-fallback upload without calling live API", () => {
    const { liveUpload } = mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, upload: FALLBACK_UPLOAD },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useUpload());
    const file = new File(["content"], "permit.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });

    expect(result.current.status).toBe("loading");
    expect(liveUpload).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(FALLBACK_UPLOAD);
    expect(result.current.error).toBeNull();
  });

  it("preserves an active fallback upload when health recovers", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, upload: FALLBACK_UPLOAD },
      status: "offline",
      retry: vi.fn(),
    });

    const { result, rerender } = renderHook(() => useUpload());
    const file = new File(["content"], "permit.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
    });
    expect(result.current.status).toBe("loading");

    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: false,
      fallbackData: null,
      status: "healthy",
      retry: vi.fn(),
    });
    mockLive();
    rerender();

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(FALLBACK_UPLOAD);
  });

  it("persists fallback upload to session storage", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, upload: FALLBACK_UPLOAD },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useUpload());
    const file = new File(["content"], "permit.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
      vi.advanceTimersByTime(400);
    });

    const stored = JSON.parse(sessionStorage.getItem("evidence-eu-document-data") ?? "{}");
    expect(stored.documentId).toBe("demo-001");
    expect(stored.filename).toBe("permit.pdf");
    expect(stored.targetLang).toBe("de");
  });

  it("reset clears demo fallback state", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, upload: FALLBACK_UPLOAD },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useUpload());
    const file = new File(["content"], "permit.pdf", { type: "application/pdf" });

    act(() => {
      result.current.upload(file, "de");
      vi.advanceTimersByTime(400);
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe("empty");
    expect(result.current.result).toBeNull();
  });

  it("passes through live upload errors", async () => {
    mockLive({
      status: "error",
      error: UPLOAD_ERROR_COPY.unavailable,
    });

    const { result } = renderHook(() => useUpload());

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(UPLOAD_ERROR_COPY.unavailable);
  });
});
