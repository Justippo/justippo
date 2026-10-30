import { describe, it, expect } from "vitest";
import { isAuthAwarePublicRoute, shouldUseAnonymousLayout } from "../anonymous-routes";

describe("shouldUseAnonymousLayout", () => {
  it("uses anonymous layout for marketing routes", () => {
    expect(shouldUseAnonymousLayout("/", false)).toBe(true);
    expect(shouldUseAnonymousLayout("/login", true)).toBe(true);
    expect(shouldUseAnonymousLayout("/public", false)).toBe(true);
  });

  it("uses anonymous layout for search/chat when logged out", () => {
    expect(shouldUseAnonymousLayout("/search", false)).toBe(true);
    expect(shouldUseAnonymousLayout("/chat", false)).toBe(true);
  });

  it("uses authenticated layout for search/chat when logged in", () => {
    expect(shouldUseAnonymousLayout("/search", true)).toBe(false);
    expect(shouldUseAnonymousLayout("/chat", true)).toBe(false);
  });

  it("identifies routes that must wait for session hydration", () => {
    expect(isAuthAwarePublicRoute("/search")).toBe(true);
    expect(isAuthAwarePublicRoute("/chat")).toBe(true);
    expect(isAuthAwarePublicRoute("/login")).toBe(false);
  });

  it("uses authenticated layout for protected routes", () => {
    expect(shouldUseAnonymousLayout("/dashboard", false)).toBe(false);
    expect(shouldUseAnonymousLayout("/upload", true)).toBe(false);
  });
});
