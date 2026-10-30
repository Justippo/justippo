import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SettingsLayout } from "./SettingsLayout";
import { SETTINGS_SECTIONS } from "@/data/mockData";

describe("SettingsLayout", () => {
  it("renders section navigation", () => {
    render(
      <SettingsLayout
        sections={SETTINGS_SECTIONS}
        activeSection="profile"
        onSectionChange={vi.fn()}
      >
        <p>Panel content</p>
      </SettingsLayout>
    );

    expect(screen.getByTestId("settings-nav-profile")).toBeDefined();
    expect(screen.getByTestId("settings-nav-compliance")).toBeDefined();
    expect(screen.getByText("Panel content")).toBeDefined();
  });
});
