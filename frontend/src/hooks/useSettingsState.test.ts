import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSettingsState } from "./useSettingsState";

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

describe("useSettingsState", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it("starts with default settings", async () => {
    const { result } = renderHook(() => useSettingsState());
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.settings.theme).toBe("system");
    expect(result.current.settings.language).toBe("en");
    expect(result.current.settings.notifications).toBe(true);
  });

  it("reads from localStorage", async () => {
    localStorageMock.getItem.mockReturnValueOnce(
      JSON.stringify({ theme: "dark", language: "de", notifications: false })
    );
    const { result } = renderHook(() => useSettingsState());
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.settings.theme).toBe("dark");
  });

  it("updateSettings changes state", async () => {
    const { result } = renderHook(() => useSettingsState());
    await waitFor(() => expect(result.current.status).toBe("success"));
    act(() => {
      result.current.updateSettings({ theme: "light" });
    });
    expect(result.current.settings.theme).toBe("light");
    expect(result.current.saved).toBe(false);
  });

  it("save writes to localStorage", async () => {
    const { result } = renderHook(() => useSettingsState());
    await waitFor(() => expect(result.current.status).toBe("success"));
    act(() => {
      result.current.save();
    });
    expect(localStorageMock.setItem).toHaveBeenCalled();
    expect(result.current.saved).toBe(true);
  });
});
