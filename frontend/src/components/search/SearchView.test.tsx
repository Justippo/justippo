import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SearchView } from "./SearchView";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/useSearch", () => ({
  useSearch: () => ({
    results: [],
    status: "empty",
    error: null,
    retry: vi.fn(),
    search: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    loginWithCredentials: vi.fn(),
  }),
}));

describe("SearchView", () => {
  it("renders search form", () => {
    render(<SearchView forcedState="empty" />);
    expect(screen.getByRole("search")).toBeDefined();
  });

  it("shows public corpus badge", () => {
    render(<SearchView forcedState="empty" />);
    expect(screen.getByTestId("search-corpus-badge")).toHaveTextContent("Public corpus — EUR-Lex");
  });

  it("shows empty state text", () => {
    render(<SearchView forcedState="empty" />);
    expect(screen.getByText(/Search public EU legal documents/)).toBeDefined();
  });

  it("renders forced success state with results", () => {
    render(<SearchView forcedState="success" />);
    expect(screen.getByTestId("search-source-list")).toBeDefined();
  });

  it("renders forced loading state with skeleton", () => {
    render(<SearchView forcedState="loading" />);
    expect(screen.getByLabelText("Searching")).toBeDefined();
  });

  it("renders forced error state", () => {
    render(<SearchView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
