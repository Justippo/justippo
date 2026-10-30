"use client";

import { Skeleton, SkeletonText } from "@/components/atoms";
import { useLandingPage } from "@/hooks/useLandingPage";
import { CtaSection } from "./CtaSection";
import { HeroSection } from "./HeroSection";
import { ProblemSection } from "./ProblemSection";
import { ScrollNarrative } from "./ScrollNarrative";
import { SolutionSection } from "./SolutionSection";
import { TrustSection } from "./TrustSection";
import { MigrationStatsCard } from "@/components/dashboard/MigrationStatsCard";
import styles from "./LandingView.module.css";

interface LandingViewProps {
  readonly forcedState?: "loading" | "success" | "error" | "empty";
}

export function LandingView({ forcedState }: Readonly<LandingViewProps>) {
  const { viewState, hero, problem, pillars, trustItems, cta, narrativeSteps } = useLandingPage({
    forcedState,
  });

  if (viewState === "loading") {
    return (
      <div className={styles.loading} aria-busy="true" aria-label="Loading landing page">
        <Skeleton height="18rem" />
        <SkeletonText lines={4} />
        <SkeletonText lines={3} />
      </div>
    );
  }

  if (viewState === "error") {
    return (
      <div className={styles.statePanel} role="alert">
        <h1 className={styles.stateTitle}>We could not load this page</h1>
        <p className={styles.stateBody}>
          Something went wrong while preparing the landing experience. Refresh the page or continue
          to search.
        </p>
        <a href="/search" className={styles.stateAction}>
          Search documents
        </a>
      </div>
    );
  }

  if (viewState === "empty") {
    return (
      <div className={styles.statePanel}>
        <h1 className={styles.stateTitle}>Welcome to EvidenceEU</h1>
        <p className={styles.stateBody}>Create an account to start working with your documents.</p>
        <a href="/register" className={styles.stateAction}>
          Get started free
        </a>
      </div>
    );
  }

  return (
    <>
      <HeroSection
        headline={hero.headline}
        subheadline={hero.subheadline}
        primaryCta={hero.primaryCta}
        primaryHref={hero.primaryHref}
        secondaryCta={hero.secondaryCta}
        secondaryHref={hero.secondaryHref}
      />
      <ScrollNarrative steps={narrativeSteps}>
        <ProblemSection headline={problem.headline} points={problem.points} />
        <SolutionSection pillars={pillars} />
        <TrustSection items={trustItems} />
        <CtaSection headline={cta.headline} buttonLabel={cta.buttonLabel} href={cta.href} />
      </ScrollNarrative>
      <MigrationStatsCard className={styles.migrationCard} />
    </>
  );
}
