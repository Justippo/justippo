// SPDX-License-Identifier: MIT
/**
 * Shared Datadog RUM + Logs configuration — imported by the DatadogInit
 * client component to avoid duplicating config (DRY).
 *
 * Env vars (all safe for browser — client token ≠ API key by design):
 *   NEXT_PUBLIC_DATADOG_APPLICATION_ID — Datadog RUM application ID
 *   NEXT_PUBLIC_DATADOG_CLIENT_TOKEN   — Datadog RUM client token (public-safe)
 *
 * NOTE: DATADOG_API_KEY is SERVER-ONLY. Never expose it to the browser.
 * It is used only in backend/app/integrations/datadog.py for custom metrics.
 */

export const DATADOG_APPLICATION_ID = process.env.NEXT_PUBLIC_DATADOG_APPLICATION_ID || "";
export const DATADOG_CLIENT_TOKEN = process.env.NEXT_PUBLIC_DATADOG_CLIENT_TOKEN || "";

/** No-op guard: if either var is unset, Datadog init is skipped entirely. */
export function isDatadogEnabled(): boolean {
  return !!DATADOG_APPLICATION_ID && !!DATADOG_CLIENT_TOKEN;
}

/** Shared base init options for RUM. */
export function getRumConfig(env: string | undefined) {
  const isProd = env === "production";
  return {
    applicationId: DATADOG_APPLICATION_ID,
    clientToken: DATADOG_CLIENT_TOKEN,
    site: "us5.datadoghq.com",
    service: "evidence-eu-frontend",
    env: env ?? "development",
    version: "0.1.0",
    sessionSampleRate: 100,
    sessionReplaySampleRate: isProd ? 20 : 100,
    trackUserInteractions: true,
    trackResources: true,
    trackLongTasks: true,
    defaultPrivacyLevel: "mask" as const,
  };
}

/** Shared base init options for Logs. */
export function getLogsConfig(env: string | undefined) {
  return {
    clientToken: DATADOG_CLIENT_TOKEN,
    site: "us5.datadoghq.com",
    service: "evidence-eu-frontend",
    env: env ?? "development",
    forwardErrors: true,
  };
}
