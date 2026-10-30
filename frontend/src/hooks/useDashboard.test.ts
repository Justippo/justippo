import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockRetry = vi.fn();
const mockUseOfflineMode = vi.fn();

vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

import { useDashboard } from "./useDashboard";

describe("useDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOfflineMode.mockReturnValue({ status: "healthy", retry: mockRetry });
  });

  it("uses the real health state without fabricated workspace collections", () => {
    const { result } = renderHook(() => useDashboard());

    expect(result.current.viewState).toBe("success");
    expect(result.current.statusCards).toEqual(
      expect.arrayContaining([expect.objectContaining({ label: "API", badgeText: "Online" })])
    );
    expect(result.current).not.toHaveProperty("activity");
    expect(result.current).not.toHaveProperty("documents");
    expect(result.current).not.toHaveProperty("searches");
    expect(result.current).not.toHaveProperty("stats");
  });

  it("reports an unavailable API without substituting sample history", () => {
    mockUseOfflineMode.mockReturnValue({ status: "offline", retry: mockRetry });
    const { result } = renderHook(() => useDashboard());

    expect(result.current.viewState).toBe("success");
    expect(result.current.statusCards).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "API",
          badgeText: "Temporarily unavailable",
          badgeVariant: "warning",
        }),
      ])
    );
  });

  it("preserves loading and recoverable error states", () => {
    mockUseOfflineMode.mockReturnValue({ status: "connecting", retry: mockRetry });
    const { result, rerender } = renderHook(() => useDashboard());
    expect(result.current.viewState).toBe("loading");

    mockUseOfflineMode.mockReturnValue({ status: "error", retry: mockRetry });
    rerender();
    expect(result.current.viewState).toBe("error");
    expect(result.current.retry).toBe(mockRetry);
  });
});
