"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/atoms";
import {
  useOnboarding,
  type OnboardingLanguage,
  type OnboardingUseCase,
} from "@/hooks/useOnboarding";
import styles from "./AuthScreens.module.css";

interface OnboardingViewProps {
  readonly forcedState?: "loading" | "success" | "error" | "empty";
}

const LANGUAGE_OPTIONS: readonly { value: OnboardingLanguage; label: string }[] = [
  { value: "EN", label: "English" },
  { value: "DE", label: "German" },
  { value: "FR", label: "French" },
];

const USE_CASE_OPTIONS: readonly { value: OnboardingUseCase; label: string }[] = [
  { value: "personal", label: "Personal" },
  { value: "legal", label: "Legal professional" },
  { value: "hr", label: "HR team" },
  { value: "researcher", label: "Researcher" },
];

export function OnboardingView({ forcedState }: Readonly<OnboardingViewProps>) {
  const router = useRouter();
  const onboarding = useOnboarding({
    forcedState,
    onComplete: () => router.push("/dashboard"),
  });

  if (onboarding.viewState === "loading") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.loadingState} role="status" aria-label="Saving preferences">
            <p>Saving your preferences…</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div
          className={styles.progress}
          role="group"
          aria-label={`Step ${onboarding.step} of ${onboarding.totalSteps}`}
        >
          {Array.from({ length: onboarding.totalSteps }).map((_, index) => (
            <span
              key={index}
              className={`${styles.progressStep} ${
                index < onboarding.step ? styles.progressStepActive : ""
              }`}
            />
          ))}
        </div>

        {onboarding.formError && (
          <p className={styles.formError} role="alert">
            {onboarding.formError}
          </p>
        )}

        {onboarding.step === 1 && (
          <>
            <h1 className={styles.heading}>Choose your primary language</h1>
            <p className={styles.subheading}>You can change this later in settings.</p>
            <div className={styles.optionGrid}>
              {LANGUAGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`${styles.optionButton} ${
                    onboarding.language === option.value ? styles.optionButtonSelected : ""
                  }`}
                  onClick={() => onboarding.setLanguage(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className={styles.actions}>
              <span />
              <Button variant="primary" onClick={onboarding.goNext}>
                Continue
              </Button>
            </div>
          </>
        )}

        {onboarding.step === 2 && (
          <>
            <h1 className={styles.heading}>How will you use EvidenceEU?</h1>
            <p className={styles.subheading}>This helps us tailor your workspace.</p>
            <div className={styles.optionGrid}>
              {USE_CASE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`${styles.optionButton} ${
                    onboarding.useCase === option.value ? styles.optionButtonSelected : ""
                  }`}
                  onClick={() => onboarding.setUseCase(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className={styles.actions}>
              <Button variant="secondary" onClick={onboarding.goBack}>
                Back
              </Button>
              <Button variant="primary" onClick={onboarding.goNext}>
                Continue
              </Button>
            </div>
          </>
        )}

        {onboarding.step === 3 && (
          <>
            <h1 className={styles.heading}>You&apos;re ready.</h1>
            <p className={styles.subheading}>
              Your workspace is configured. Upload a document or search the public corpus.
            </p>
            <div className={styles.actions}>
              <Button variant="secondary" onClick={onboarding.goBack}>
                Back
              </Button>
              <Button
                variant="primary"
                onClick={onboarding.complete}
                data-testid="onboarding-finish"
              >
                Go to dashboard
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
