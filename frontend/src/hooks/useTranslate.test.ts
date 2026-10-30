import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockUseTranslationState = vi.fn();
vi.mock("./useTranslationState", () => ({
  useTranslationState: () => mockUseTranslationState(),
}));

const mockUseOfflineMode = vi.fn();
vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

import { useTranslate } from "./useTranslate";
import { TRANSLATION_ERROR_COPY } from "@/data/mockData";

const FALLBACK_TRANSLATE = {
  job_id: "demo-job-001",
  status: "done",
  translated_pages: [
    {
      page: 1,
      text: "EU-Aufenthaltstitel-Antragsformular\n\nFeld 1: Vollständiger Name — John Smith",
    },
  ],
  error: null,
} as const;

const TRUNCATED_FALLBACK = {
  job_id: "demo-job-002",
  status: "done",
  translated_pages: [{ page: 1, text: "Translated text[truncated]" }],
  error: null,
} as const;

function mockLive(overrides: Partial<ReturnType<typeof mockUseTranslationState>> = {}) {
  const liveTranslate = vi.fn();
  const liveReset = vi.fn();
  mockUseTranslationState.mockReturnValue({
    status: "empty",
    result: null,
    error: null,
    isTruncated: false,
    translate: liveTranslate,
    reset: liveReset,
    ...overrides,
  });
  return { liveTranslate, liveReset };
}

describe("useTranslate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
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

  it("starts in empty state via live translation", () => {
    const { result } = renderHook(() => useTranslate());
    expect(result.current.status).toBe("empty");
    expect(result.current.result).toBeNull();
    expect(result.current.isTruncated).toBe(false);
  });

  it("delegates translate to live API when healthy", () => {
    const { liveTranslate } = mockLive();
    const { result } = renderHook(() => useTranslate());
    const pages = [{ page: 1, text: "Hello" }];

    act(() => {
      result.current.translate("doc-1", "en", "de", pages);
    });

    expect(liveTranslate).toHaveBeenCalledWith("doc-1", "en", "de", pages);
  });

  it("serves demo-fallback translation without calling live API", () => {
    const { liveTranslate } = mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, translate: FALLBACK_TRANSLATE },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useTranslate());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello" }]);
    });

    expect(result.current.status).toBe("loading");
    expect(liveTranslate).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(400);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(FALLBACK_TRANSLATE);
    expect(result.current.isTruncated).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("detects truncation suffix in demo-fallback results", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, translate: TRUNCATED_FALLBACK },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useTranslate());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Long text" }]);
      vi.advanceTimersByTime(400);
    });

    expect(result.current.isTruncated).toBe(true);
  });

  it("reset clears demo fallback state", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, translate: FALLBACK_TRANSLATE },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useTranslate());

    act(() => {
      result.current.translate("doc-1", "en", "de", [{ page: 1, text: "Hello" }]);
      vi.advanceTimersByTime(400);
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe("empty");
    expect(result.current.result).toBeNull();
    expect(result.current.isTruncated).toBe(false);
  });

  it("passes through live translation errors", () => {
    mockLive({
      status: "error",
      error: TRANSLATION_ERROR_COPY.unavailable,
    });

    const { result } = renderHook(() => useTranslate());

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(TRANSLATION_ERROR_COPY.unavailable);
  });
});
