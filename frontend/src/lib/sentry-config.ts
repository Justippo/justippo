// SPDX-License-Identifier: MIT
/**
 * Shared Sentry configuration — imported by both instrumentation-client.ts
 * and sentry.server.config.ts to avoid duplicating DSN, environment, and
 * sampling rate settings (DRY).
 *
 * Env vars:
 *   NEXT_PUBLIC_SENTRY_DSN       — Sentry project DSN (build-time, safe for browser)
 *   SENTRY_AUTH_TOKEN             — auth token for sourcemap upload (server/CI only)
 *   SENTRY_ORG                    — Sentry org slug (for withSentryConfig in next.config.js)
 *   SENTRY_PROJECT                — Sentry project slug
 */

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || "";

/** No-op guard: if DSN is unset, Sentry init is skipped entirely. */
export function isSentryEnabled(): boolean {
  return !!SENTRY_DSN;
}

/** Base init options shared across client and server. */
export function getBaseSentryOptions(env: string | undefined) {
  const isProd = env === "production";
  return {
    dsn: SENTRY_DSN,
    environment: env ?? "development",
    // Capture 100% in dev, 10% in production
    tracesSampleRate: isProd ? 0.1 : 1.0,
  };
}
