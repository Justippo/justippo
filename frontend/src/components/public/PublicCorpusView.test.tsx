import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PublicCorpusView } from "./PublicCorpusView";

describe("PublicCorpusView", () => {
  it("renders corpus title in success state", () => {
    render(<PublicCorpusView forcedState="success" />);
    expect(screen.getByText("EU Public Document Corpus")).toBeDefined();
  });

  it("shows EUR-Lex source badge", () => {
    render(<PublicCorpusView forcedState="success" />);
    expect(screen.getByTestId("public-corpus-source")).toHaveTextContent("Powered by EUR-Lex");
  });

  it("lists featured documents", () => {
    render(<PublicCorpusView forcedState="success" />);
    expect(screen.getAllByTestId("public-corpus-doc").length).toBeGreaterThan(0);
  });

  it("renders loading state", () => {
    render(<PublicCorpusView forcedState="loading" />);
    expect(screen.getByLabelText("Loading public corpus")).toBeDefined();
  });

  it("renders error state", () => {
    render(<PublicCorpusView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
