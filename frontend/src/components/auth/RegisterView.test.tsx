import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RegisterView } from "./RegisterView";

describe("RegisterView", () => {
  it("renders registration form", () => {
    render(<RegisterView forcedState="empty" />);
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeDefined();
    expect(screen.getByLabelText("Password requirements")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<RegisterView forcedState="loading" />);
    expect(screen.getByLabelText("Creating account")).toBeDefined();
  });

  it("renders error state", () => {
    render(<RegisterView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });
});
