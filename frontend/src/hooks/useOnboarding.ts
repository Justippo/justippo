"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type OnboardingViewState = "loading" | "success" | "error" | "empty";

export type OnboardingLanguage = "EN" | "DE" | "FR";
export type OnboardingUseCase = "personal" | "legal" | "hr" | "researcher";

interface UseOnboardingOptions {
  readonly onComplete?: () => void;
  readonly forcedState?: OnboardingViewState;
}

interface UseOnboardingResult {
  readonly viewState: OnboardingViewState;
  readonly step: number;
  readonly totalSteps: number;
  readonly language: OnboardingLanguage | null;
  readonly useCase: OnboardingUseCase | null;
  readonly formError: string | null;
  readonly setLanguage: (value: OnboardingLanguage) => void;
  readonly setUseCase: (value: OnboardingUseCase) => void;
  readonly goNext: () => void;
  readonly goBack: () => void;
  readonly complete: () => void;
}

export function useOnboarding({
  onComplete,
  forcedState,
}: Readonly<UseOnboardingOptions> = {}): UseOnboardingResult {
  const [viewState, setViewState] = useState<OnboardingViewState>("empty");
  const [step, setStep] = useState(1);
  const [language, setLanguage] = useState<OnboardingLanguage | null>(null);
  const [useCase, setUseCase] = useState<OnboardingUseCase | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const completeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (completeTimerRef.current) {
        clearTimeout(completeTimerRef.current);
        completeTimerRef.current = null;
      }
    };
  }, []);

  const goNext = useCallback(() => {
    if (step === 1 && !language) {
      setViewState("error");
      setFormError("Choose your primary language to continue.");
      return;
    }
    if (step === 2 && !useCase) {
      setViewState("error");
      setFormError("Choose how you plan to use EvidenceEU.");
      return;
    }
    setFormError(null);
    setViewState("empty");
    setStep((prev) => Math.min(prev + 1, 3));
  }, [language, step, useCase]);

  const goBack = useCallback(() => {
    setFormError(null);
    setViewState("empty");
    setStep((prev) => Math.max(prev - 1, 1));
  }, []);

  const complete = useCallback(() => {
    if (!language || !useCase) {
      setViewState("error");
      setFormError("Complete each step before continuing.");
      return;
    }
    setViewState("loading");
    if (completeTimerRef.current) {
      clearTimeout(completeTimerRef.current);
    }
    completeTimerRef.current = setTimeout(() => {
      completeTimerRef.current = null;
      if (!mountedRef.current) return;
      setViewState("success");
      onComplete?.();
    }, 500);
  }, [language, onComplete, useCase]);

  if (forcedState) {
    return {
      viewState: forcedState,
      step: forcedState === "success" ? 3 : 1,
      totalSteps: 3,
      language: forcedState === "empty" ? null : "EN",
      useCase: forcedState === "empty" ? null : "legal",
      formError: forcedState === "error" ? "Choose your primary language to continue." : null,
      setLanguage: () => {},
      setUseCase: () => {},
      goNext: () => {},
      goBack: () => {},
      complete: () => {},
    };
  }

  return {
    viewState,
    step,
    totalSteps: 3,
    language,
    useCase,
    formError,
    setLanguage,
    setUseCase,
    goNext,
    goBack,
    complete,
  };
}
