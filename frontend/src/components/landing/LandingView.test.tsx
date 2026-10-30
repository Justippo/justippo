import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { LandingView } from "./LandingView";

// Mock problematic components that use different React versions
vi.mock("./MigrationStatsCard", () => ({
  MigrationStatsCard: () => <div data-testid="migration-stats-card">Migration Stats Mock</div>,
}));

vi.mock("./HeroSection", () => ({
  HeroSection: ({
    headline,
    subheadline,
    primaryCta,
    primaryHref,
    secondaryCta,
    secondaryHref,
  }: any) => (
    <section data-testid="hero-section">
      <h1>{headline}</h1>
      <p>{subheadline}</p>
      <a href={primaryHref}>{primaryCta}</a>
      <a href={secondaryHref}>{secondaryCta}</a>
    </section>
  ),
}));

vi.mock("./ProblemSection", () => ({
  ProblemSection: ({ headline, points }: any) => (
    <section data-testid="problem-section">
      <h2>{headline}</h2>
      <ul>
        {points.map((p: string) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </section>
  ),
}));

vi.mock("./SolutionSection", () => ({
  SolutionSection: ({ pillars }: any) => (
    <section data-testid="solution-section">
      <h2>One platform. Three pillars.</h2>
      {pillars.map((p: any) => (
        <article key={p.id}>
          <h3>{p.title}</h3>
          <p>{p.description}</p>
        </article>
      ))}
    </section>
  ),
}));

vi.mock("./TrustSection", () => ({
  TrustSection: ({ items }: any) => (
    <section data-testid="trust-section">
      <h2>Built for EU compliance</h2>
      {items.map((item: any) => (
        <div key={item.id}>
          <h3>{item.title}</h3>
          <p>{item.description}</p>
        </div>
      ))}
    </section>
  ),
}));

vi.mock("./CtaSection", () => ({
  CtaSection: ({ headline, buttonLabel, href }: any) => (
    <section data-testid="cta-section">
      <h2>{headline}</h2>
      <a href={href}>{buttonLabel}</a>
    </section>
  ),
}));

describe("LandingView", () => {
  it("renders success narrative", () => {
    render(<LandingView forcedState="success" />);
    expect(screen.getByText("Document intelligence for a borderless Europe.")).toBeDefined();
    expect(screen.getByText("Built for EU compliance")).toBeDefined();
    expect(screen.getByText("Start for free. No credit card required.")).toBeDefined();
    // Mock TrustSection doesn't render links, just headings
    expect(screen.getByText("GDPR-native processing")).toBeDefined();
    expect(screen.getByText("Formatting preserved")).toBeDefined();
    expect(screen.getByText("Built for professionals")).toBeDefined();
  });

  it("renders loading state", () => {
    render(<LandingView forcedState="loading" />);
    expect(screen.getByLabelText("Loading landing page")).toBeDefined();
  });

  it("renders error state", () => {
    render(<LandingView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
  });

  it("renders empty state", () => {
    render(<LandingView forcedState="empty" />);
    expect(screen.getByText("Welcome to EvidenceEU")).toBeDefined();
  });
});
