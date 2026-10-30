/**
 * Sentry server-side (Node.js / Edge) configuration for Next.js App Router.
 *
 * This file is loaded on the server (Node.js runtime via instrumentation.ts).
 * No replay integration needed — replays are browser-side only.
 * Server-side spans will show 0ms on Cloudflare Workers due to the V8 isolate
 * security model (timers don't advance during CPU-bound work). This is expected.
 */

import * as Sentry from "@sentry/nextjs";
import { getBaseSentryOptions, isSentryEnabled } from "@/lib/sentry-config";

if (isSentryEnabled()) {
  Sentry.init({
    ...getBaseSentryOptions(process.env.NODE_ENV),
  });
}
