import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSettingsView } from "./useSettingsView";

vi.mock("./useT", () => ({
  useT: () => ({
    t: (key: string) => key,
    language: "en",
    changeLanguage: vi.fn().mockResolvedValue(undefined),
  }),
}));

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

describe("useSettingsView", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it("returns forced compliance section on success", () => {
    const { result } = renderHook(() => useSettingsView({ forcedState: "success" }));
    expect(result.current.viewState).toBe("success");
    expect(result.current.activeSection).toBe("compliance");
    expect(result.current.gdprDomains).toHaveLength(8);
  });

  it("returns empty state without active section", () => {
    const { result } = renderHook(() => useSettingsView({ forcedState: "empty" }));
    expect(result.current.activeSection).toBeNull();
  });

  it("loads live settings after hydration", async () => {
    const { result } = renderHook(() => useSettingsView());
    await waitFor(() => expect(result.current.viewState).toBe("success"));
    expect(result.current.activeSection).toBe("profile");
  });

  it("changes active section", async () => {
    const { result } = renderHook(() => useSettingsView());
    await waitFor(() => expect(result.current.viewState).toBe("success"));
    act(() => {
      result.current.setActiveSection("accessibility");
    });
    expect(result.current.activeSection).toBe("accessibility");
  });
});
