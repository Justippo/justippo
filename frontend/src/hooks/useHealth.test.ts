import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockCheckHealth = vi.fn();
vi.mock("@/lib/api-generated", () => ({
  checkHealth: (...args: unknown[]) => mockCheckHealth(...args),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

import { useHealth } from "./useHealth";

describe("useHealth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns healthy on successful health check", async () => {
    mockCheckHealth.mockResolvedValue({ status: "ok", version: "1.0.0", sprint: 3 });
    const { result } = renderHook(() => useHealth());
    expect(result.current.status).toBe("connecting");
    await waitFor(() => expect(result.current.status).toBe("healthy"));
    expect(result.current.isOfflineMode).toBe(false);
    expect(mockCheckHealth).toHaveBeenCalled();
  });

  it("returns offline mode after 3 failures and loads fallback", async () => {
    const fallbackData = { fallbackMode: true, upload: { doc_id: "test" } };
    mockCheckHealth.mockRejectedValue(new Error("network"));
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fallbackData),
    });

    const { result } = renderHook(() => useHealth());
    await waitFor(() => expect(result.current.status).toBe("offline"), { timeout: 10000 });
    expect(result.current.isOfflineMode).toBe(true);
    expect(result.current.fallbackData).toEqual(fallbackData);
    expect(mockCheckHealth).toHaveBeenCalledTimes(3);
    expect(mockFetch).toHaveBeenCalledWith("/demo-fallback.json");
  });

  it("returns error when health and fallback both fail", async () => {
    mockCheckHealth.mockRejectedValue(new Error("network"));
    mockFetch.mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useHealth());
    await waitFor(() => expect(result.current.status).toBe("error"), { timeout: 10000 });
    expect(result.current.isOfflineMode).toBe(false);
    expect(result.current.fallbackData).toBeNull();
    expect(mockCheckHealth).toHaveBeenCalledTimes(3);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
