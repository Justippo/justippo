import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OnboardingView } from "./OnboardingView";

describe("OnboardingView", () => {
  it("renders step one", () => {
    render(<OnboardingView forcedState="empty" />);
    expect(screen.getByText("Choose your primary language")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<OnboardingView forcedState="loading" />);
    expect(screen.getByLabelText("Saving preferences")).toBeDefined();
  });

  it("renders error state", () => {
    render(<OnboardingView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
