import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChatView } from "./ChatView";

describe("ChatView", () => {
  it("renders heading", () => {
    render(<ChatView forcedState="success" />);
    expect(screen.getByText("Ask a legal question")).toBeDefined();
  });

  it("renders public corpus badge", () => {
    render(<ChatView forcedState="success" />);
    expect(screen.getByTestId("chat-corpus-badge")).toHaveTextContent("Public corpus — EUR-Lex");
  });

  it("renders conversation messages in success state", () => {
    render(<ChatView forcedState="success" />);
    expect(screen.getByLabelText("Conversation")).toBeDefined();
  });

  it("shows sign-in prompt for logged-out users", () => {
    render(<ChatView forcedState="empty" />);
    expect(screen.getByText("Sign in")).toBeDefined();
  });

  it("renders error state", () => {
    render(<ChatView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
