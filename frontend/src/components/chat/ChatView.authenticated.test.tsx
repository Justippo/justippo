import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ChatView } from "./ChatView";

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    loginWithCredentials: vi.fn(),
  }),
}));

describe("ChatView authenticated", () => {
  it("shows personal corpus badge when authenticated", () => {
    render(<ChatView forcedState="success" />);
    expect(screen.getByTestId("chat-corpus-badge")).toHaveTextContent("Public corpus — EUR-Lex");
  });

  it("enables chat input for authenticated users", () => {
    render(<ChatView forcedState="empty" />);
    expect(screen.getByLabelText("What would you like to know about EU law?")).not.toBeDisabled();
  });

  it("keeps Send disabled until the question has content", () => {
    render(<ChatView forcedState="empty" />);
    const sendButton = screen.getByRole("button", { name: "Send" });
    expect(sendButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("What would you like to know about EU law?"), {
      target: { value: "What are the Spanish remote-work tax rules?" },
    });

    expect(sendButton).toBeEnabled();
  });

  it("does not show sign-in prompt when authenticated", () => {
    render(<ChatView forcedState="empty" />);
    expect(screen.queryByText("Sign in")).toBeNull();
  });
});
