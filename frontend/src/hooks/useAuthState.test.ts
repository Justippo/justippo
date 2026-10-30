import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuthState } from "./useAuthState";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock BroadcastChannel to prevent cross-test message leakage.
// Without this, async logout()'s postMessage("logout") can be delivered
// to a subsequent test's hook listener, causing false failures.
const postMessage = vi.fn();
const close = vi.fn();
vi.stubGlobal(
  "BroadcastChannel",
  class {
    constructor() {}
    postMessage = postMessage;
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    close = close;
  }
);

describe("useAuthState", () => {
  beforeEach(() => {
    localStorageMock.clear();
    try {
      sessionStorage.clear();
    } catch {
      // sessionStorage unavailable in some environments
    }
    vi.clearAllMocks();
  });

  it("starts unauthenticated and loading", () => {
    const { result } = renderHook(() => useAuthState());
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("reads auth from localStorage", async () => {
    localStorageMock.getItem.mockReturnValueOnce("true");
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("login sets authenticated and persists", async () => {
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.login();
    });
    expect(result.current.isAuthenticated).toBe(true);
    expect(localStorageMock.setItem).toHaveBeenCalledWith("evidenceeu_auth", "true");
  });

  it("logout clears authentication", async () => {
    localStorageMock.getItem.mockReturnValueOnce("true");
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.logout();
    });
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("evidenceeu_auth");
  });

  it("loginWithCredentials accepts demo credentials", async () => {
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let ok = false;
    act(() => {
      ok = result.current.loginWithCredentials("test@test.com", "test123");
    });
    expect(ok).toBe(true);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("loginWithCredentials rejects invalid credentials", async () => {
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let ok = true;
    act(() => {
      ok = result.current.loginWithCredentials("wrong@example.eu", "bad");
    });
    expect(ok).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("bfcache pageshow revalidation clears stale auth on restore", async () => {
    localStorageMock.getItem.mockReturnValueOnce("true");
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(true);

    await act(async () => {
      await result.current.logout();
    });

    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    });
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("pageshow without persisted does not reset auth", async () => {
    localStorageMock.getItem.mockReturnValueOnce("true");
    const { result } = renderHook(() => useAuthState());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
    });
    expect(result.current.isAuthenticated).toBe(true);
  });
});
