import { screen, within } from "@testing-library/react";
import { beforeEach, describe, it, expect } from "vitest";
import { AuthProvider } from "@/context/AuthContext";
import { BottomNav } from "./BottomNav";
import { renderWithI18n as render } from "@/test-utils";

function renderWithAuth() {
  return render(
    <AuthProvider>
      <BottomNav />
    </AuthProvider>
  );
}

describe("BottomNav", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders mobile navigation", () => {
    renderWithAuth();
    expect(screen.getByLabelText("Mobile navigation")).toBeDefined();
  });

  it("renders the canonical public navigation", () => {
    renderWithAuth();

    const navigation = screen.getByLabelText("Mobile navigation");
    expect(
      within(navigation)
        .getAllByRole("link")
        .map((link) => link.textContent)
    ).toEqual(["Search", "Chat", "Translate"]);
  });

  it("renders the canonical authenticated navigation", async () => {
    localStorage.setItem("evidenceeu_auth", "true");
    renderWithAuth();

    const navigation = screen.getByLabelText("Mobile navigation");
    expect(
      (await within(navigation).findAllByRole("link")).map((link) => link.textContent)
    ).toEqual(["Search", "Chat", "Translate", "Dashboard", "Exchange"]);
  });
});
