import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ConnectingOverlay } from "./ConnectingOverlay";

vi.mock("@/hooks/useHealth", () => ({
  useHealth: () => ({
    status: "connecting",
    isOfflineMode: false,
    fallbackData: null,
    retry: vi.fn(),
  }),
}));

describe("ConnectingOverlay", () => {
  it("renders children without connecting copy", () => {
    render(
      <ConnectingOverlay>
        <p>App content</p>
      </ConnectingOverlay>
    );
    expect(screen.getByText("App content")).toBeDefined();
    expect(screen.queryByText(/Connecting to backend/i)).toBeNull();
    expect(screen.queryByText(/Connecting/i)).toBeNull();
  });
});
