import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useCompareState } from "./useCompareState";

describe("useCompareState", () => {
  it("starts in empty state", () => {
    const { result } = renderHook(() => useCompareState());
    expect(result.current.status).toBe("empty");
    expect(result.current.blocks).toEqual([]);
  });

  it("computes diff and transitions to success", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCompareState());
    act(() => {
      result.current.compare("Hello World", "Hello Earth");
    });
    expect(result.current.status).toBe("loading");
    act(() => {
      vi.runAllTimers();
    });
    expect(result.current.status).toBe("success");
    expect(result.current.blocks.length).toBeGreaterThan(0);
    vi.useRealTimers();
  });

  it("reset clears state", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCompareState());
    act(() => {
      result.current.compare("a", "b");
    });
    act(() => {
      vi.runAllTimers();
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.status).toBe("empty");
    vi.useRealTimers();
  });
});
