"use client";

/**
 * MOBILE_GAP: localStorage/cookie-based consent storage.
 * Mobile requires AsyncStorage-backed consent store.
 * See docs/mobile/mobile-compat.md for the adaptation plan.
 */

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { initPostHog, optInCapturing, optOutCapturing } from "@/lib/posthog";

// DRY: GDPR consent context — single source of truth for consent state.
// Used by useAnalytics, PostHog gating, and all GDPR-sensitive features.

const CONSENT_KEY = "evidence-eu-gdpr-consent";
const CONSENT_VALUE = "granted";

interface GDPRConsentValue {
  readonly hasConsent: boolean;
  readonly grantConsent: () => void;
  readonly revokeConsent: () => void;
}

const GDPRConsentContext = createContext<GDPRConsentValue>({
  hasConsent: false,
  grantConsent: () => {},
  revokeConsent: () => {},
});

interface GDPRConsentProviderProps {
  readonly children: React.ReactNode;
}

export function GDPRConsentProvider({ children }: Readonly<GDPRConsentProviderProps>) {
  const [hasConsent, setHasConsent] = useState(false);

  // Initialize PostHog on mount (suspended by default)
  useEffect(() => {
    initPostHog();
    // Read persisted consent from localStorage
    try {
      const stored = localStorage.getItem(CONSENT_KEY);
      if (stored === CONSENT_VALUE) {
        setHasConsent(true);
        optInCapturing();
      }
    } catch {
      // localStorage unavailable (SSR or privacy mode)
    }
  }, []);

  const grantConsent = useCallback(() => {
    setHasConsent(true);
    optInCapturing();
    try {
      localStorage.setItem(CONSENT_KEY, CONSENT_VALUE);
    } catch {
      // localStorage unavailable
    }
  }, []);

  const revokeConsent = useCallback(() => {
    setHasConsent(false);
    optOutCapturing();
    try {
      localStorage.removeItem(CONSENT_KEY);
    } catch {
      // localStorage unavailable
    }
  }, []);

  return (
    <GDPRConsentContext.Provider value={{ hasConsent, grantConsent, revokeConsent }}>
      {children}
    </GDPRConsentContext.Provider>
  );
}

export function useGDPRConsent(): GDPRConsentValue {
  return useContext(GDPRConsentContext);
}
