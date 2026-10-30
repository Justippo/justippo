import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { LoginView } from "./LoginView";

describe("LoginView", () => {
  it("renders sign-in form in empty state", () => {
    render(<LoginView forcedState="empty" />);
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeDefined();
    expect(screen.getByTestId("login-email")).toBeDefined();
    expect(screen.queryByText(/Matrix/)).toBeNull();
  });

  it("renders loading state", () => {
    render(<LoginView forcedState="loading" />);
    expect(screen.getByLabelText("Signing in")).toBeDefined();
  });

  it("renders error state", () => {
    render(<LoginView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
