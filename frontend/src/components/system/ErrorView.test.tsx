import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorView } from "./ErrorView";

describe("ErrorView", () => {
  it("renders friendly error copy without raw error details", () => {
    render(<ErrorView />);
    expect(screen.getByTestId("error-view")).toBeDefined();
    expect(screen.getByText("Something went wrong")).toBeDefined();
    expect(screen.queryByText(/stack trace/i)).toBeNull();
  });

  it("renders retry action when provided", () => {
    render(<ErrorView onRetry={vi.fn()} />);
    expect(screen.getByTestId("error-retry")).toBeDefined();
  });
});
