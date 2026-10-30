"use client";

/**
 * MOBILE_GAP: posthog-js is web-only. Mobile uses posthog-react-native.
 * The event names and properties in this file are shared-compatible.
 * See docs/mobile/mobile-compat.md.
 */

import { useCallback } from "react";
import { getPostHog, getFlag as getPostHogFlag } from "@/lib/posthog";
import { useGDPRConsent } from "@/context/GDPRConsentContext";

// DRY: typed analytics event hook — all events are no-ops when consent is not active.
// Components call this hook — never posthog.capture() directly.

interface UploadEventProps {
  readonly page_count: number;
  readonly content_type: string;
  readonly target_language: string;
  readonly document_type: string;
  readonly has_explanation: boolean;
}

interface SearchEventProps {
  readonly language: string;
  readonly result_count: number;
  readonly query_length: number;
  readonly has_answer: boolean;
}

interface TranslationEventProps {
  readonly source_language: string;
  readonly target_language: string;
  readonly page_count: number;
  readonly glossary_terms_applied: number;
  readonly has_quality_report: boolean;
  readonly status: string;
}

interface ExchangeEventProps {
  readonly protocol: string;
  readonly direction: "send" | "receive";
}

interface ErrorEventProps {
  readonly error_type: string;
  readonly error_message: string;
  readonly status_code: number;
  readonly route: string;
}

interface AnalyticsHook {
  readonly trackUpload: (props: UploadEventProps) => void;
  readonly trackSearch: (props: SearchEventProps) => void;
  readonly trackTranslation: (props: TranslationEventProps) => void;
  readonly trackExchange: (props: ExchangeEventProps) => void;
  readonly trackError: (props: ErrorEventProps) => void;
  readonly getFlag: (flagKey: string) => boolean;
  readonly isEnabled: boolean;
}

export function useAnalytics(): AnalyticsHook {
  const { hasConsent } = useGDPRConsent();

  const trackUpload = useCallback(
    (props: UploadEventProps) => {
      if (!hasConsent) return;
      getPostHog()?.capture("document_uploaded", props);
    },
    [hasConsent]
  );

  const trackSearch = useCallback(
    (props: SearchEventProps) => {
      if (!hasConsent) return;
      getPostHog()?.capture("search_performed", props);
    },
    [hasConsent]
  );

  const trackTranslation = useCallback(
    (props: TranslationEventProps) => {
      if (!hasConsent) return;
      getPostHog()?.capture("document_translated", props);
    },
    [hasConsent]
  );

  const trackExchange = useCallback(
    (props: ExchangeEventProps) => {
      if (!hasConsent) return;
      getPostHog()?.capture("exchange_document_shared", props);
    },
    [hasConsent]
  );

  const trackError = useCallback(
    (props: ErrorEventProps) => {
      if (!hasConsent) return;
      getPostHog()?.capture("error_occurred", props);
    },
    [hasConsent]
  );

  return {
    trackUpload,
    trackSearch,
    trackTranslation,
    trackExchange,
    trackError,
    getFlag: getPostHogFlag,
    isEnabled: hasConsent,
  };
}
