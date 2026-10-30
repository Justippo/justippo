import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePrimaryNavigation } from "./usePrimaryNavigation";
import { TestI18nProvider } from "@/test-utils";

describe("usePrimaryNavigation", () => {
  it("returns the public navigation in product order", () => {
    const { result } = renderHook(() => usePrimaryNavigation(false), {
      wrapper: TestI18nProvider,
    });

    expect(result.current).toEqual([
      { href: "/search", label: "Search" },
      { href: "/chat", label: "Chat" },
      { href: "/translation", label: "Translate" },
    ]);
  });

  it("appends authenticated destinations in product order", () => {
    const { result } = renderHook(() => usePrimaryNavigation(true), {
      wrapper: TestI18nProvider,
    });

    expect(result.current).toEqual([
      { href: "/search", label: "Search" },
      { href: "/chat", label: "Chat" },
      { href: "/translation", label: "Translate" },
      { href: "/dashboard", label: "Dashboard" },
      { href: "/exchange", label: "Exchange" },
    ]);
  });
});
