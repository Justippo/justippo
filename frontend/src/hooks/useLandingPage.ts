"use client";

import { useMemo } from "react";
import {
  LANDING_HERO,
  LANDING_PROBLEM,
  LANDING_SOLUTION_PILLARS,
  LANDING_TRUST_ITEMS,
  LANDING_CTA,
  LANDING_NARRATIVE_STEPS,
} from "@/data/mockData";

export type LandingViewState = "loading" | "success" | "error" | "empty";

interface UseLandingPageOptions {
  readonly forcedState?: LandingViewState;
}

interface UseLandingPageResult {
  readonly viewState: LandingViewState;
  readonly hero: typeof LANDING_HERO;
  readonly problem: typeof LANDING_PROBLEM;
  readonly pillars: typeof LANDING_SOLUTION_PILLARS;
  readonly trustItems: typeof LANDING_TRUST_ITEMS;
  readonly cta: typeof LANDING_CTA;
  readonly narrativeSteps: typeof LANDING_NARRATIVE_STEPS;
}

export function useLandingPage({
  forcedState,
}: Readonly<UseLandingPageOptions> = {}): UseLandingPageResult {
  const viewState: LandingViewState = forcedState ?? "success";

  return useMemo(
    () => ({
      viewState,
      hero: LANDING_HERO,
      problem: LANDING_PROBLEM,
      pillars: LANDING_SOLUTION_PILLARS,
      trustItems: LANDING_TRUST_ITEMS,
      cta: LANDING_CTA,
      narrativeSteps: LANDING_NARRATIVE_STEPS,
    }),
    [viewState]
  );
}
