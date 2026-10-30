import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSearchPage } from "./useSearchPage";

const state = vi.hoisted(() => ({ authenticated: false }));
const sourceUrl = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: state.authenticated,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    loginWithCredentials: vi.fn(),
  }),
}));

vi.mock("./useSearchView", () => ({
  useSearchView: () => ({
    status: "success",
    results: [
      {
        id: "result-1",
        text: "Residence rights under Directive 2004/38/EC.",
        type: "world",
        chunk_id: "chunk-1",
        entities: [],
        rank: 1,
        source_url: sourceUrl,
        source_title: "Directive 2004/38/EC",
        source_language: "en",
      },
    ],
    error: null,
    retry: vi.fn(),
    query: "residence permit",
    setQuery: vi.fn(),
    handleSubmit: vi.fn(),
  }),
}));

describe("useSearchPage citation presentation", () => {
  beforeEach(() => {
    state.authenticated = false;
  });

  it("routes anonymous readers through the citation gateway", () => {
    const { result } = renderHook(() => useSearchPage());

    expect(result.current.results[0].citationHref).toMatch(/^\/citation\?/);
    expect(result.current.results[0].citationTarget).toBeUndefined();
  });

  it("keeps direct official links for authenticated readers", () => {
    state.authenticated = true;
    const { result } = renderHook(() => useSearchPage());

    expect(result.current.results[0].citationHref).toBe(sourceUrl);
    expect(result.current.results[0].citationTarget).toBe("_blank");
  });
});
