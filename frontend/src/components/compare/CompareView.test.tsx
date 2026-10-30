import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CompareView } from "./CompareView";

describe("CompareView", () => {
  it("renders empty state heading", () => {
    render(<CompareView forcedState="empty" />);
    expect(screen.getByText("Compare documents")).toBeDefined();
  });

  it("renders success state with diff blocks", () => {
    render(<CompareView forcedState="success" />);
    expect(screen.getByText("Document comparison")).toBeDefined();
    expect(screen.getAllByTestId("compare-block").length).toBeGreaterThan(0);
    expect(screen.getByTestId("compare-filename")).toBeDefined();
  });

  it("renders error state", () => {
    render(<CompareView forcedState="error" />);
    expect(screen.getByTestId("compare-error")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<CompareView forcedState="loading" />);
    expect(screen.getByLabelText("Computing differences")).toBeDefined();
  });

  it("renders diff view toggle button in success state", () => {
    render(<CompareView forcedState="success" />);
    const toggle = screen.getByTestId("compare-toggle-view");
    expect(toggle).toBeDefined();
    expect(toggle.textContent).toContain("Side by side");
  });
});
