import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SearchView } from "./SearchView";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/useSearchPage", () => ({
  useSearchPage: () => ({
    viewState: "success",
    corpusLabel: "EN → DE",
    searchPlaceholder: "Search documents…",
    emptyText: "",
    emptyHintSuffix: "",
    results: [
      {
        id: "1",
        text: "GDPR compliance applies to all EU data controllers.",
        type: "world",
        chunk_id: "c1",
        rank: 1,
        entities: [],
        source_url: "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679",
        source_title: "Regulation (EU) 2016/679",
        source_language: "en",
        citationHref: "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679",
        citationTarget: "_blank",
      },
      {
        id: "2",
        text: "Saved only: local processing rules.",
        type: "saved",
        chunk_id: "c2",
        rank: 2,
        entities: [],
        source_url: null,
      },
    ],
    error: null,
    retry: vi.fn(),
    query: "GDPR",
    setQuery: vi.fn(),
    handleSubmit: vi.fn((e) => e.preventDefault()),
  }),
}));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    loginWithCredentials: vi.fn(),
  }),
}));

describe("SearchView authenticated", () => {
  it("shows truthful result ranks and a verified citation", () => {
    render(<SearchView forcedState="success" />);
    expect(screen.getByText("Rank 1")).toBeInTheDocument();
    expect(screen.getByText("Rank 2")).toBeInTheDocument();
    expect(screen.queryByText(/confidence/)).not.toBeInTheDocument();
    const citation = screen.getByRole("link", { name: "View cited document" });
    expect(citation).toHaveAttribute(
      "href",
      "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679"
    );
    expect(citation).toHaveAttribute("target", "_blank");
    expect(citation).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not offer a citation action without verified provenance", () => {
    render(<SearchView forcedState="success" />);
    expect(screen.getAllByRole("link", { name: "View cited document" })).toHaveLength(1);
  });

  it("renders result text content", () => {
    render(<SearchView forcedState="success" />);
    expect(screen.getByText(/GDPR compliance/)).toBeTruthy();
    expect(screen.getByText(/Saved only/)).toBeTruthy();
  });
});
