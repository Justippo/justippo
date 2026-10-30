import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/context/AuthContext";
import { Sidebar } from "./Sidebar";
import { renderWithI18n as render } from "@/test-utils";

const mockPathname = vi.fn(() => "/");
vi.mock("next/navigation", async () => {
  const actual = await vi.importActual<typeof import("next/navigation")>("next/navigation");
  return { ...actual, usePathname: () => mockPathname() };
});

function renderSidebar() {
  return render(
    <AuthProvider>
      <Sidebar isOpen onClose={vi.fn()} />
    </AuthProvider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
    mockPathname.mockReturnValue("/");
  });

  it("renders the canonical public navigation", () => {
    renderSidebar();

    const navigation = screen.getByLabelText("Sidebar navigation");
    expect(
      within(navigation)
        .getAllByRole("link")
        .map((link) => link.textContent)
    ).toEqual(["Search", "Chat", "Translate"]);
  });

  it("renders the canonical authenticated navigation", async () => {
    localStorage.setItem("evidenceeu_auth", "true");
    renderSidebar();

    const navigation = screen.getByLabelText("Sidebar navigation");
    expect(
      (await within(navigation).findAllByRole("link")).map((link) => link.textContent)
    ).toEqual(["Search", "Chat", "Translate", "Dashboard", "Exchange"]);
  });

  it("marks the active route with aria-current='page'", () => {
    mockPathname.mockReturnValue("/chat");
    renderSidebar();

    const navigation = screen.getByLabelText("Sidebar navigation");
    const active = within(navigation).getByRole("link", { name: "Chat" });
    expect(active).toHaveAttribute("aria-current", "page");

    const inactive = within(navigation).getByRole("link", { name: "Search" });
    expect(inactive).not.toHaveAttribute("aria-current");
  });
});
