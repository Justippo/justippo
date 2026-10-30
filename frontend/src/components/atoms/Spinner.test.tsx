import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Spinner } from "./Spinner";

describe("Spinner", () => {
  it("has role=status", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeDefined();
  });

  it("has accessible label", () => {
    render(<Spinner aria-label="Processing" />);
    expect(screen.getByLabelText("Processing")).toBeDefined();
  });
});
