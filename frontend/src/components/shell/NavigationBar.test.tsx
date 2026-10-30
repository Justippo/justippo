import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { NavigationBar } from "./NavigationBar";
import { AuthProvider } from "@/context/AuthContext";
import { renderWithI18n as render } from "@/test-utils";

// Use the real useT hook so language switching resolves German locale text.
vi.unmock("@/hooks/useT");

function renderWithAuth() {
  return render(
    <AuthProvider>
      <NavigationBar />
    </AuthProvider>
  );
}

describe("NavigationBar", () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = "NEXT_LOCALE=; Max-Age=0; Path=/";
    document.documentElement.lang = "en";
  });

  it("renders brand link", () => {
    renderWithAuth();
    expect(screen.getByLabelText("EvidenceEU home")).toBeDefined();
  });

  it("renders skip-to-content link", () => {
    renderWithAuth();
    expect(screen.getByText("Skip to content")).toBeDefined();
  });

  it("does not render primary navigation links in top navbar", () => {
    renderWithAuth();
    expect(screen.queryByLabelText("Main navigation")).toBeNull();
  });

  it("renders authenticated account settings link", async () => {
    localStorage.setItem("evidenceeu_auth", "true");
    renderWithAuth();

    expect(await screen.findByRole("link", { name: "Account settings" })).toHaveAttribute(
      "href",
      "/settings"
    );
  });

  it("changes and persists the interface language", async () => {
    localStorage.setItem("evidenceeu_auth", "true");
    renderWithAuth();

    const languageSelect = await screen.findByTestId("interface-language-select");
    fireEvent.change(languageSelect, { target: { value: "de" } });

    await waitFor(() => {
      expect(languageSelect).toHaveValue("de");
      expect(screen.getByText("Abmelden")).toBeInTheDocument();
    });
    expect(document.documentElement.lang).toBe("de");
    expect(localStorage.getItem("evidenceeu_interface_language")).toBe("de");
    expect(document.cookie).toContain("NEXT_LOCALE=de");
  });
});
