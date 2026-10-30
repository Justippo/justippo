import { screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AppShell } from "./AppShell";
import { renderWithI18n as render } from "@/test-utils";

const shellState = vi.hoisted(() => ({
  pathname: "/dashboard",
  auth: {
    isAuthenticated: true,
    isLoading: false,
    isMatrixAuthEnabled: true,
    login: vi.fn(),
    loginWithCredentials: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => shellState.pathname,
}));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => shellState.auth,
}));

const mockUseOfflineMode = vi.fn<
  [],
  {
    status: "healthy" | "offline" | "connecting" | "error";
    isOfflineMode: boolean;
    fallbackData: null;
    retry: ReturnType<typeof vi.fn>;
  }
>(() => ({
  status: "healthy" as const,
  isOfflineMode: false,
  fallbackData: null,
  retry: vi.fn(),
}));

vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));

describe("AppShell", () => {
  beforeEach(() => {
    shellState.pathname = "/dashboard";
    shellState.auth.isAuthenticated = true;
    shellState.auth.isLoading = false;
    mockUseOfflineMode.mockReturnValue({
      status: "healthy",
      isOfflineMode: false,
      fallbackData: null,
      retry: vi.fn(),
    });
  });

  it("renders main content area", () => {
    render(
      <AppShell>
        <p>Test content</p>
      </AppShell>
    );
    expect(screen.getByText("Test content")).toBeDefined();
  });

  it("has main landmark with id", () => {
    render(
      <AppShell>
        <p>Content</p>
      </AppShell>
    );
    expect(document.getElementById("main-content")).toBeDefined();
  });

  it("has aria-live region for SSE on authenticated routes", () => {
    render(
      <AppShell>
        <p>Content</p>
      </AppShell>
    );
    expect(document.getElementById("sse-announcements")).toBeDefined();
  });

  it("shows offline banner when viewing sample data", () => {
    mockUseOfflineMode.mockReturnValue({
      status: "offline",
      isOfflineMode: true,
      fallbackData: null,
      retry: vi.fn(),
    });

    render(
      <AppShell>
        <p>Content</p>
      </AppShell>
    );

    expect(screen.getByTestId("offline-banner")).toBeDefined();
    expect(screen.getByText("You're viewing sample data.")).toBeDefined();
  });

  it("does not flash the signed-out search shell while restoring a session", () => {
    shellState.pathname = "/search";
    shellState.auth.isAuthenticated = false;
    shellState.auth.isLoading = true;

    const { rerender } = render(
      <AppShell>
        <p>Search content</p>
      </AppShell>
    );

    expect(screen.getByRole("status", { name: "Checking session" })).toBeDefined();
    expect(screen.queryByText("Search content")).toBeNull();
    expect(screen.queryByText("Sign in")).toBeNull();

    shellState.auth.isAuthenticated = true;
    shellState.auth.isLoading = false;
    rerender(
      <AppShell>
        <p>Search content</p>
      </AppShell>
    );

    expect(screen.getByText("Search content")).toBeDefined();
    expect(screen.getByTestId("nav-btn-logout")).toBeDefined();
  });
});
