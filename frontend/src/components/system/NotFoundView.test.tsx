import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { NotFoundView } from "./NotFoundView";

describe("NotFoundView", () => {
  it("renders not found copy and home link", () => {
    render(<NotFoundView />);
    expect(screen.getByTestId("not-found-view")).toBeDefined();
    expect(screen.getByText("Page not found")).toBeDefined();
    expect(screen.getByText("Go to home")).toBeDefined();
  });
});
