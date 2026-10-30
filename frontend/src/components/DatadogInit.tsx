"use client";
// SPDX-License-Identifier: MIT

/**
 * Datadog RUM + Logs initialization — client-only component.
 *
 * This component is imported by RootLayout (a server component) to ensure
 * Datadog SDKs are initialized in the browser only, not during SSR/SSG.
 * Uses dynamic import to avoid loading the SDK on the server.
 */

import { useDatadogInit } from "@/hooks/useDatadogInit";

export function DatadogInit() {
  useDatadogInit();

  return null;
}
