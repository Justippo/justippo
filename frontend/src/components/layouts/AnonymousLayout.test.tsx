import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AnonymousLayout } from "./AnonymousLayout";
import { renderWithI18n as render } from "@/test-utils";

describe("AnonymousLayout", () => {
  it("renders footer without GitHub link", () => {
    render(
      <AnonymousLayout>
        <p>Child content</p>
      </AnonymousLayout>
    );
    expect(screen.getByText("Child content")).toBeDefined();
    expect(screen.getByText("Privacy")).toBeDefined();
    expect(screen.getByText(/Quantic MSSE Capstone/)).toBeDefined();
    expect(screen.queryByText(/GitHub/)).toBeNull();
  });
});
