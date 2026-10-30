import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AuthenticatedLayout } from "./AuthenticatedLayout";
import { renderWithI18n as render } from "@/test-utils";

describe("AuthenticatedLayout", () => {
  it("renders children in main landmark", () => {
    render(
      <AuthenticatedLayout>
        <p>Workspace content</p>
      </AuthenticatedLayout>
    );
    expect(screen.getByText("Workspace content")).toBeDefined();
    expect(document.getElementById("main-content")).toBeDefined();
  });

  it("includes SSE announcement region", () => {
    render(
      <AuthenticatedLayout>
        <p>Content</p>
      </AuthenticatedLayout>
    );
    expect(document.getElementById("sse-announcements")).toBeDefined();
  });
});
