import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockUseSearchSSE = vi.fn();
vi.mock("./useSearchSSE", () => ({
  useSearchSSE: () => mockUseSearchSSE(),
}));

const mockUseOfflineMode = vi.fn();
vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

import { useSearch } from "./useSearch";
import { SEARCH_ERROR_COPY } from "@/data/mockData";

const FALLBACK_RESULTS = [
  {
    id: "chunk-demo-001",
    text: "Die Verlängerung eines Aufenthaltstitels richtet sich nach §8 AufenthG.",
    type: "world",
    chunk_id: "chunk-demo-001",
    entities: ["Aufenthaltstitel", "§8 AufenthG"],
    rank: 1,
  },
] as const;

function mockLive(overrides: Partial<ReturnType<typeof mockUseSearchSSE>> = {}) {
  const liveSearch = vi.fn();
  const liveRetry = vi.fn();
  const liveReset = vi.fn();
  mockUseSearchSSE.mockReturnValue({
    results: [],
    status: "empty",
    error: null,
    retry: liveRetry,
    search: liveSearch,
    reset: liveReset,
    ...overrides,
  });
  return { liveSearch, liveRetry, liveReset };
}

describe("useSearch", () => {
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

  it("starts in empty state via live SSE", () => {
    const { result } = renderHook(() => useSearch());
    expect(result.current.status).toBe("empty");
    expect(result.current.results).toEqual([]);
  });

  it("delegates search to live SSE when API is healthy", () => {
    const { liveSearch } = mockLive();
    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.search("GDPR Germany");
    });

    expect(liveSearch).toHaveBeenCalledWith("GDPR Germany");
  });

  it("keeps controller callbacks stable when the live hook returns a new state object", () => {
    const liveSearch = vi.fn();
    const liveRetry = vi.fn();
    const liveReset = vi.fn();
    mockUseSearchSSE.mockImplementation(() => ({
      results: [],
      status: "empty",
      error: null,
      retry: liveRetry,
      search: liveSearch,
      reset: liveReset,
    }));

    const { result, rerender } = renderHook(() => useSearch());
    const firstSearch = result.current.search;
    const firstRetry = result.current.retry;
    const firstReset = result.current.reset;

    rerender();

    expect(result.current.search).toBe(firstSearch);
    expect(result.current.retry).toBe(firstRetry);
    expect(result.current.reset).toBe(firstReset);
  });

  it("serves demo-fallback results without calling live SSE", () => {
    const { liveSearch } = mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, search: FALLBACK_RESULTS },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.search("residence permit extension Germany");
    });

    expect(result.current.status).toBe("loading");
    expect(liveSearch).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.results).toEqual(FALLBACK_RESULTS);
    expect(result.current.error).toBeNull();
  });

  it("retry re-runs fallback search in offline mode", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, search: FALLBACK_RESULTS },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.search("query");
      vi.advanceTimersByTime(300);
    });

    act(() => {
      result.current.retry();
    });

    expect(result.current.status).toBe("loading");

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(result.current.status).toBe("success");
    expect(result.current.results).toEqual(FALLBACK_RESULTS);
  });

  it("reset clears demo fallback state", () => {
    mockLive();
    mockUseOfflineMode.mockReturnValue({
      isOfflineMode: true,
      fallbackData: { fallbackMode: true, search: FALLBACK_RESULTS },
      status: "offline",
      retry: vi.fn(),
    });

    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.search("query");
      vi.advanceTimersByTime(300);
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe("empty");
    expect(result.current.results).toEqual([]);
  });

  it("passes through live SSE errors with production copy", () => {
    mockLive({
      results: [],
      status: "error",
      error: SEARCH_ERROR_COPY.unavailable,
    });

    const { result } = renderHook(() => useSearch());

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(SEARCH_ERROR_COPY.unavailable);
  });
});
