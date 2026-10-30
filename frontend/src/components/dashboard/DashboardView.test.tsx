import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DashboardView } from "./DashboardView";

vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => ({
    status: "healthy",
    isOfflineMode: false,
    fallbackData: null,
    retry: vi.fn(),
  }),
}));

describe("DashboardView", () => {
  it("renders heading", () => {
    render(<DashboardView forcedState="success" />);
    expect(screen.getByText("Dashboard")).toBeDefined();
  });

  it("shows privacy guidance and real workspace actions in success state", () => {
    render(<DashboardView forcedState="success" />);
    expect(screen.getByText("Private by design")).toBeDefined();
    expect(screen.getByRole("link", { name: "Translate document" })).toHaveAttribute(
      "href",
      "/translation?start=upload"
    );
    expect(screen.getByText("System Status")).toBeDefined();
  });

  it("does not present fabricated workspace history", () => {
    render(<DashboardView forcedState="success" />);
    expect(screen.queryByText("Workspace statistics")).toBeNull();
    expect(screen.queryByText("Recent documents")).toBeNull();
    expect(screen.queryByText("Recent searches")).toBeNull();
    expect(screen.queryByText("Recent Activity")).toBeNull();
    expect(screen.queryByText("Sample Document")).toBeNull();
    expect(screen.queryByText("GDPR compliance")).toBeNull();
  });

  it("renders empty state with upload CTA", () => {
    render(<DashboardView forcedState="empty" />);
    expect(screen.getByText("Translate your first document")).toBeDefined();
  });

  it("renders error state without backend jargon", () => {
    render(<DashboardView forcedState="error" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load dashboard data");
    expect(screen.queryByText(/backend/i)).toBeNull();
  });

  it("does not show demo mode copy", () => {
    render(<DashboardView forcedState="success" />);
    expect(screen.queryByText(/demo mode/i)).toBeNull();
  });
});
