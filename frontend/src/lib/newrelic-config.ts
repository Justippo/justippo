// SPDX-License-Identifier: MIT
/**
 * New Relic Browser Agent configuration — frontend only.
 *
 * The New Relic Python/Node.js agent cannot run in Pyodide (uses socket/threading),
 * so we use the browser agent only (same constraint as Sentry and Datadog).
 *
 * Env vars (all browser-safe — New Relic browser config is public by design):
 *   NEXT_PUBLIC_NEW_RELIC_ENABLED        — explicit opt-in feature flag (`true`)
 *   NEXT_PUBLIC_NEW_RELIC_ACCOUNT_ID     — New Relic account ID
 *   NEXT_PUBLIC_NEW_RELIC_APPLICATION_ID — New Relic browser application ID
 *   NEXT_PUBLIC_NEW_RELIC_LICENSE_KEY    — New Relic browser license key
 *   NEXT_PUBLIC_NEW_RELIC_AGENT_ID       — New Relic browser agent ID
 *   NEXT_PUBLIC_NEW_RELIC_TRUST_KEY      — New Relic trust key (usually same as account ID)
 *
 * NOTE: These are the browser-specific license key, NOT the server-side API key.
 * New Relic browser keys are designed to be public.
 */

export const NEW_RELIC_ENABLED = process.env.NEXT_PUBLIC_NEW_RELIC_ENABLED === "true";
export const NEW_RELIC_ACCOUNT_ID = process.env.NEXT_PUBLIC_NEW_RELIC_ACCOUNT_ID || "";
export const NEW_RELIC_APPLICATION_ID = process.env.NEXT_PUBLIC_NEW_RELIC_APPLICATION_ID || "";
export const NEW_RELIC_LICENSE_KEY = process.env.NEXT_PUBLIC_NEW_RELIC_LICENSE_KEY || "";
export const NEW_RELIC_AGENT_ID = process.env.NEXT_PUBLIC_NEW_RELIC_AGENT_ID || "";
export const NEW_RELIC_TRUST_KEY =
  process.env.NEXT_PUBLIC_NEW_RELIC_TRUST_KEY || NEW_RELIC_ACCOUNT_ID;

interface NewRelicEnvironment {
  readonly enabled: boolean;
  readonly accountId: string;
  readonly applicationId: string;
  readonly licenseKey: string;
}

/** Pure configuration guard used by runtime initialization and regression tests. */
export function shouldEnableNewRelic({
  enabled,
  accountId,
  applicationId,
  licenseKey,
}: NewRelicEnvironment): boolean {
  return enabled && Boolean(accountId && applicationId && licenseKey);
}

/**
 * New Relic is opt-in because Datadog and Sentry provide the primary production
 * observability surfaces. Missing the flag or any required value is a no-op.
 */
export function isNewRelicEnabled(): boolean {
  return shouldEnableNewRelic({
    enabled: NEW_RELIC_ENABLED,
    accountId: NEW_RELIC_ACCOUNT_ID,
    applicationId: NEW_RELIC_APPLICATION_ID,
    licenseKey: NEW_RELIC_LICENSE_KEY,
  });
}

/**
 * Build the New Relic browser agent inline script.
 * Uses the SPA loader from New Relic's CDN.
 *
 * Reference: https://docs.newrelic.com/docs/browser/browser-monitoring/installation/install-browser-monitoring-agent/
 */
export function getNewRelicScript(): string {
  if (!isNewRelicEnabled()) return "";

  return `
;window.NREUM||(NREUM={});
NREUM.init={distributed_tracing:{enabled:true},privacy:{cookies_enabled:true},ajax:{deny_list:["bam.nr-data.net"]}};
NREUM.loader_config={accountID:"${NEW_RELIC_ACCOUNT_ID}",trustKey:"${NEW_RELIC_TRUST_KEY}",agentID:"${NEW_RELIC_AGENT_ID}",licenseKey:"${NEW_RELIC_LICENSE_KEY}",applicationID:"${NEW_RELIC_APPLICATION_ID}"};
NREUM.info={beacon:"bam.nr-data.net",errorBeacon:"bam.nr-data.net",licenseKey:"${NEW_RELIC_LICENSE_KEY}",applicationID:"${NEW_RELIC_APPLICATION_ID}",sa:1};
`;
}

/**
 * Pinned supported SPA loader. Avoid the floating `current` alias so a New
 * Relic rollout cannot change production behavior without a code review.
 */
export const NEW_RELIC_AGENT_VERSION = "1.317.0";
export const NEW_RELIC_AGENT_URL = `https://js-agent.newrelic.com/nr-loader-spa-${NEW_RELIC_AGENT_VERSION}.min.js`;
