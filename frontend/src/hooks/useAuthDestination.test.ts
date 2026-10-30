import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { safeInternalRedirect, useAuthDestination } from "./useAuthDestination";

const navigation = vi.hoisted(() => ({
  params: new URLSearchParams(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => navigation.params,
}));

describe("useAuthDestination", () => {
  beforeEach(() => {
    navigation.params = new URLSearchParams();
  });

  it("preserves a citation return path across sign-in and sign-up", () => {
    const citationPath = "/citation?source=https%3A%2F%2Feur-lex.europa.eu%2Fdocument";
    navigation.params = new URLSearchParams({ redirect: citationPath });

    const { result } = renderHook(() => useAuthDestination("/dashboard"));

    expect(result.current.destination).toBe(citationPath);
    expect(result.current.loginHref).toContain(encodeURIComponent(citationPath));
    expect(result.current.registerHref).toContain(encodeURIComponent(citationPath));
  });

  it("rejects external and protocol-relative redirects", () => {
    expect(safeInternalRedirect("https://example.com")).toBeNull();
    expect(safeInternalRedirect("//example.com")).toBeNull();
    expect(safeInternalRedirect("/\\example.com")).toBeNull();
  });
});
