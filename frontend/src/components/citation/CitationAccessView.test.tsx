import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CitationAccessView } from "./CitationAccessView";
import { useCitationAccess } from "@/hooks/useCitationAccess";

vi.mock("@/hooks/useCitationAccess", () => ({
  useCitationAccess: vi.fn(),
}));

const mockedUseCitationAccess = vi.mocked(useCitationAccess);
const sourceUrl = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";

describe("CitationAccessView", () => {
  beforeEach(() => {
    mockedUseCitationAccess.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isValid: true,
      sourceUrl,
      sourceTitle: "Directive 2004/38/EC",
      signInHref: "/login?redirect=%2Fcitation",
      signUpHref: "/register?redirect=%2Fcitation",
    });
  });

  it("prompts anonymous readers to sign in or create an account", () => {
    render(<CitationAccessView />);

    expect(screen.getByRole("heading", { name: "Directive 2004/38/EC" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login?redirect=%2Fcitation"
    );
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute(
      "href",
      "/register?redirect=%2Fcitation"
    );
    expect(screen.queryByRole("link", { name: /Open official document/ })).toBeNull();
  });

  it("offers the verified official document to authenticated readers", () => {
    mockedUseCitationAccess.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      isValid: true,
      sourceUrl,
      sourceTitle: "Directive 2004/38/EC",
      signInHref: "/login",
      signUpHref: "/register",
    });

    render(<CitationAccessView />);

    const link = screen.getByRole("link", { name: /Open official document/ });
    expect(link).toHaveAttribute("href", sourceUrl);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("rejects an unverified citation", () => {
    mockedUseCitationAccess.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isValid: false,
      sourceUrl: null,
      sourceTitle: "Unknown source",
      signInHref: "/login",
      signUpHref: "/register",
    });

    render(<CitationAccessView />);

    expect(screen.getByRole("alert")).toHaveTextContent("Citation unavailable");
    expect(screen.getByRole("link", { name: "Return to search" })).toHaveAttribute(
      "href",
      "/search"
    );
  });
});
