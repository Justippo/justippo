import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScrollNarrative } from "./ScrollNarrative";
import { renderWithProviders } from "@/test-utils";

const STEPS = [
  { id: "challenge", label: "The challenge" },
  { id: "start", label: "Start now" },
] as const;

describe("ScrollNarrative", () => {
  it("renders all content panels with correct IDs", () => {
    renderWithProviders(
      <ScrollNarrative steps={STEPS}>
        <section>Challenge content</section>
        <section>Action content</section>
      </ScrollNarrative>
    );

    expect(screen.getByText("Challenge content")).toBeDefined();
    expect(screen.getByText("Action content")).toBeDefined();
  });

  it("rejects an incomplete step definition", () => {
    expect(() =>
      renderWithProviders(
        <ScrollNarrative steps={STEPS}>
          <section>Only one panel</section>
        </ScrollNarrative>
      )
    ).toThrow("one child panel for every journey step");
  });
});
