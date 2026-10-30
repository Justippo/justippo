import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Input } from "./Input";

describe("Input", () => {
  it("renders with placeholder", () => {
    render(<Input id="test" placeholder="Type here" />);
    expect(screen.getByPlaceholderText("Type here")).toBeDefined();
  });

  it("calls onChange", () => {
    const onChange = vi.fn();
    render(<Input id="test" onChange={onChange} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hello" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("is disabled when disabled prop set", () => {
    render(<Input id="test" disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});
