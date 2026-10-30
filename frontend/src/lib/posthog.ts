"use client";

import posthog from "posthog-js";
import type { PostHogInterface } from "posthog-js";

// DRY: PostHog JS SDK singleton — matches the no-op pattern used by backend integrations.
// Init is suspended by default; opt_in_capturing() is called only after GDPR consent.

let _initialized = false;
let _ph: PostHogInterface | null = null;

const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://eu.i.posthog.com";

/**
 * Initialize the PostHog JS SDK in a suspended/opted-out state.
 * Call once on mount in the root layout. No-op if already initialized
 * or if NEXT_PUBLIC_POSTHOG_KEY is unset.
 */
export function initPostHog(): void {
  // Read env at call time (not module load) so tests can set it per-test
  const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (_initialized || !POSTHOG_KEY) return;

  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    opt_out_capturing_by_default: true, // GDPR: suspended until consent
    capture_pageview: true, // PostHog dashboard $pageview health check
    disable_session_recording: true, // enabled after consent via startSessionRecording()
    persistence: "localStorage", // no cookies — avoids cookie consent overlap
    ip: false, // GDPR: no IP capture
    loaded: (ph) => {
      _ph = ph;
      _initialized = true;
    },
  });
}

/**
 * Return the PostHog instance, or null if not initialized.
 * Components must check consent state before calling opt_in_capturing().
 */
export function getPostHog(): PostHogInterface | null {
  return _ph;
}

/**
 * Opt in to capturing after GDPR consent is confirmed.
 * Enables session recording with full masking.
 */
export function optInCapturing(): void {
  if (!_ph) return;
  _ph.opt_in_capturing();
  // Workaround for posthog-js#336: sessions don't record when opting in
  // after opt_out_capturing_by_default. Use disable_session_recording config
  // toggle instead of startSessionRecording() — the SDK checks this flag
  // on each recording decision rather than requiring an explicit start call.
  _ph.set_config({
    disable_session_recording: false,
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: "[data-sensitive]",
    },
  });
}

/**
 * Opt out of capturing when GDPR consent is revoked.
 * Stops session recording immediately.
 */
export function optOutCapturing(): void {
  if (!_ph) return;
  // Mirror of opt-in workaround: use config toggle instead of stopSessionRecording
  _ph.set_config({ disable_session_recording: true });
  _ph.opt_out_capturing();
}

/**
 * Reset the PostHog singleton. For tests only.
 * @internal
 */
export function _resetPostHogForTests(): void {
  _initialized = false;
  _ph = null;
}

/**
 * Feature flag evaluation. Returns false when PostHog is uninitialized
 * or the flag is not found. Safe to call before consent.
 */
export function getFlag(flagKey: string): boolean {
  if (!_ph) return false;
  try {
    return _ph.isFeatureEnabled(flagKey) === true;
  } catch {
    return false;
  }
}
