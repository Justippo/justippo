import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, "localStorage", { value: localStorageMock });

function TestConsumer() {
  const { isAuthenticated, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{isAuthenticated ? "logged-in" : "anonymous"}</span>
      <button onClick={login}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it("starts as anonymous", () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );
    expect(screen.getByTestId("status").textContent).toBe("anonymous");
  });

  it("login toggles to authenticated", () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("Login"));
    });
    expect(screen.getByTestId("status").textContent).toBe("logged-in");
    expect(localStorageMock.setItem).toHaveBeenCalledWith("evidenceeu_auth", "true");
  });

  it("logout toggles back to anonymous", () => {
    localStorageMock.getItem.mockReturnValueOnce("true");
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );
    act(() => {
      fireEvent.click(screen.getByText("Logout"));
    });
    expect(screen.getByTestId("status").textContent).toBe("anonymous");
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("evidenceeu_auth");
  });
});
