import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RequireAuth } from "./RequireAuth";
import { AuthProvider } from "@/context/AuthContext";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace,
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  usePathname: () => "/upload",
  useSearchParams: () => new URLSearchParams(),
}));

describe("RequireAuth", () => {
  beforeEach(() => {
    replace.mockClear();
    window.localStorage.clear();
  });

  it("redirects unauthenticated users to login", async () => {
    render(
      <AuthProvider>
        <RequireAuth>
          <p>Protected</p>
        </RequireAuth>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login?redirect=%2Fupload");
    });
    expect(screen.queryByText("Protected")).toBeNull();
  });
});
