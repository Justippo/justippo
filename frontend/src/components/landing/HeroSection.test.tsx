import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { HeroSection } from "./HeroSection";

describe("HeroSection", () => {
  it("renders headline and CTAs", () => {
    const { container } = render(
      <HeroSection
        headline="Document intelligence for a borderless Europe."
        subheadline="Search, translate, and exchange."
        primaryCta="Get started free"
        primaryHref="/register"
        secondaryCta="See how it works"
        secondaryHref="#how-it-works"
      />
    );
    expect(screen.getByText("Document intelligence for a borderless Europe.")).toBeDefined();
    expect(screen.getByRole("link", { name: "Get started free" })).toBeDefined();
    expect(screen.queryByText(/Connecting to backend/)).toBeNull();
    expect(screen.queryByText(/Demo mode/)).toBeNull();
    const heroImage = container.querySelector("picture img");
    const sources = container.querySelectorAll("picture source");
    expect(heroImage).toHaveAttribute("fetchpriority", "high");
    expect(heroImage).toHaveAttribute("loading", "eager");
    expect(sources).toHaveLength(2);
    expect(sources[0]).toHaveAttribute("type", "image/avif");
    expect(sources[0]).toHaveAttribute("srcset", expect.stringContaining("hero-640.avif 640w"));
    expect(sources[1]).toHaveAttribute("type", "image/webp");
  });
});
