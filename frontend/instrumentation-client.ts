// SPDX-License-Identifier: MIT
/**
 * Sentry client-side (browser) configuration for Next.js App Router.
 *
 * Replaces the deprecated `sentry.client.config.ts` convention (removed in
 * @sentry/nextjs v9+/v10, and required for Next.js 15+/Turbopack). Next.js
 * loads this file automatically in the browser runtime.
 *
 * Enables:
 *   - Error capture from React components
 *   - Performance tracing via tracesSampleRate
 *   - Session Replay (browser-only)
 *
 * Do NOT import server-only modules here.
 */

import { replayIntegration } from "@sentry/browser";
import * as Sentry from "@sentry/nextjs";
import { getBaseSentryOptions, isSentryEnabled } from "@/lib/sentry-config";
import { filterBrowserSentryEvent } from "@/lib/sentry-event-filter";

/**
 * Patch console.assert to handle null-prototype objects gracefully.
 *
 * @tolgee/web (all builds) calls:
 *   console.assert(FastTextEncoding)
 * where FastTextEncoding is built with `_mergeNamespaces({ __proto__: null })`.
 * Next.js dev-mode wraps console.assert and calls String() on ALL arguments —
 * including the condition — which throws "Cannot convert object to primitive
 * value" because null-prototype objects have no toString().
 *
 * This patch runs before TolgeeClientProvider mounts and replaces
 * console.assert with a version that catches only that TypeError, re-throwing
 * all other assertion errors so legitimate React errors are still surfaced.
 *
 * Bug: https://github.com/tolgee/tolgee-js/issues (FastTextEncoding assertion)
 */
if (process.env.NODE_ENV === "development") {
  const _origAssert = console.assert.bind(console);
  // eslint-disable-next-line no-console
  console.assert = function safeAssert(condition?: boolean, ...data: unknown[]): void {
    try {
      _origAssert(condition, ...data);
    } catch (e) {
      if (e instanceof TypeError && (e as TypeError).message.includes("primitive")) {
        return; // swallow only null-prototype stringify errors from Tolgee
      }
      throw e;
    }
  };
}


if (isSentryEnabled()) {
  Sentry.init({
    ...getBaseSentryOptions(process.env.NODE_ENV),
    beforeSend: filterBrowserSentryEvent,

    // Replay: capture 10% of sessions, 100% of sessions with errors
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,

    integrations: [
      replayIntegration({
        // Replays are privacy-sensitive — mask all text by default
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
  });
}

// Track App Router navigations as spans (SDK >= 9.12)
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
