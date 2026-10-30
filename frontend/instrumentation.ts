/**
 * Next.js Instrumentation — registers Sentry on server startup.
 *
 * This file is loaded by Next.js before the server starts handling requests.
 * It imports the appropriate Sentry config based on the runtime (Node.js vs Edge).
 *
 * See: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.server.config");
  }
}

// Capture errors from Server Components, middleware, and route handlers
export const onRequestError = Sentry.captureRequestError;
