import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ExchangeView } from "./ExchangeView";

describe("ExchangeView", () => {
  it("renders empty state with create room form", () => {
    render(<ExchangeView forcedState="empty" />);
    expect(screen.getByText("Document exchange")).toBeDefined();
    expect(screen.getByTestId("exchange-create")).toBeDefined();
    expect(screen.getByTestId("exchange-participant-input")).toBeDefined();
  });

  it("renders success state with room details", () => {
    render(<ExchangeView forcedState="success" />);
    expect(screen.getByTestId("exchange-room-name").textContent).toContain("Residence permit");
    expect(screen.getByTestId("exchange-room-status").textContent).toBe("Active");
    expect(screen.getByText("Participants")).toBeDefined();
  });

  it("renders error state", () => {
    render(<ExchangeView forcedState="error" />);
    expect(screen.getByTestId("exchange-error")).toBeDefined();
    expect(screen.getByTestId("exchange-error-action").textContent).toBe("Try again");
  });

  it("renders loading state", () => {
    render(<ExchangeView forcedState="loading" />);
    expect(screen.getByLabelText("Creating exchange room")).toBeDefined();
  });
});
