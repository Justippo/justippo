import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Tag } from "./Tag";

describe("Tag", () => {
  it("renders children", () => {
    render(<Tag>PDF</Tag>);
    expect(screen.getByText("PDF")).toBeDefined();
  });

  it("shows remove button when onRemove provided", () => {
    const onRemove = vi.fn();
    render(<Tag onRemove={onRemove}>EN</Tag>);
    const btn = screen.getByRole("button", { name: "Remove" });
    fireEvent.click(btn);
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it("hides remove button when no onRemove", () => {
    render(<Tag>FR</Tag>);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
