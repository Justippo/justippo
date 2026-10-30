import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SettingsView } from "./SettingsView";

vi.mock("@/hooks/useT", () => ({
  useT: () => ({
    t: (key: string) => key,
    language: "en",
    changeLanguage: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("SettingsView", () => {
  it("renders compliance GDPR domains on success", () => {
    render(<SettingsView forcedState="success" />);
    expect(screen.getByTestId("settings-layout")).toBeDefined();
    expect(screen.getByTestId("settings-gdpr-domains")).toBeDefined();
    expect(screen.getAllByText("Pass").length).toBe(8);
  });

  it("renders empty state prompt", () => {
    render(<SettingsView forcedState="empty" />);
    expect(screen.getByText("Choose a category")).toBeDefined();
  });

  it("renders error state", () => {
    render(<SettingsView forcedState="error" />);
    expect(screen.getByTestId("settings-error")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<SettingsView forcedState="loading" />);
    expect(screen.getByLabelText("Loading settings")).toBeDefined();
  });

  it("renders save button when a section is active", () => {
    render(<SettingsView forcedState="success" />);
    expect(screen.getByTestId("settings-save")).toBeDefined();
  });
});
