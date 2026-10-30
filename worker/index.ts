// MIGRATION: Modal stopped 2026-07-21. Services moving to local + CF Tunnel.
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * EvidenceEU — Cloudflare Worker Entry Point
 *
 * Responsibilities:
 * - Proxy all /api/v1/* requests to the FastAPI backend origin
 * - Pass through original request headers including CF-Ray
 * - Read the FastAPI origin URL from the FASTAPI_ORIGIN environment variable
 * - Short-circuit feature-flagged routes at the edge (defense in depth)
 * - Expose edge liveness probes (/__warm, /health) for monitoring
 * - Return all other requests (incl. root `/`, owned by the frontend) with a 404
 */

import * as Sentry from "@sentry/cloudflare";

const ALLOWED_ORIGINS = [
  "https://evidence-eu-frontend.pages.dev",
  "http://localhost:3000",
];

function corsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get("Origin") ?? "";
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers":
      "Content-Type, Authorization, X-GDPR-Consent, X-Request-ID",
    "Access-Control-Max-Age": "86400",
  };
}

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;

function requestIdFor(request: Request): string {
  const supplied = request.headers.get("X-Request-ID");
  return supplied && REQUEST_ID_PATTERN.test(supplied)
    ? supplied
    : crypto.randomUUID();
}

export interface Env {
  /** Base URL of the FastAPI backend, e.g. https://evidence-eu-api.mc146.workers.dev */
  FASTAPI_ORIGIN: string;
  /** Service binding to the backend worker (preferred over HTTP fetch) */
  BACKEND?: { fetch: (req: Request) => Promise<Response> };
  /** Feature flag: Matrix cross-border document exchange (Sprint 3) */
  ENABLE_MATRIX_EXCHANGE?: string;
  /** Sentry DSN for error monitoring (unset → no-op, graceful degradation) */
  SENTRY_DSN?: string;
  /** D1 database binding for session cleanup (shared with backend) */
  DB?: D1Database;

}

export default Sentry.withSentry(
  (env: Env) => ({
    dsn: env.SENTRY_DSN || "",
    environment: "production",
    tracesSampleRate: 0.1,
  }),
  {
    async fetch(request: Request, env: Env): Promise<Response> {
      const url = new URL(request.url);

      // ── Edge liveness probes ──────────────────────────────────────────────────
      // Lightweight endpoints that return immediately without forwarding to the
      // backend. Used by monitoring (Cloudflare Health Checks) and the post-deploy
      // smoke test. `/__warm` additionally warms the proxy isolate to avoid TLS
      // connection resets (curl 000) from simultaneous handshakes to a freshly
      // deployed Worker.
      if (url.pathname === "/__warm" || url.pathname === "/health") {
        return new Response("OK", { status: 200 });
      }

      // Only proxy /api/v1/* — let everything else fall through to a 404
      if (!url.pathname.startsWith("/api/v1/")) {
        return new Response("Not Found", { status: 404 });
      }

      // Handle CORS preflight (OPTIONS) for all /api/v1/* routes.
      // Must return before any feature-flag gates so preflight always succeeds.
      // See GitHub issue #275.
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: corsHeaders(request) });
      }

      // Edge-level feature flag short-circuit for Matrix exchange routes.
      // Does not forward to FastAPI at all when ENABLE_MATRIX_EXCHANGE is not "true".
      // Non-OPTIONS requests get a 403 with CORS headers so the browser can read the error.
      if (url.pathname.startsWith("/api/v1/exchange/")) {
        if (env.ENABLE_MATRIX_EXCHANGE !== "true") {
          return new Response(
            JSON.stringify({
              detail: "feature not enabled",
              flag: "ENABLE_MATRIX_EXCHANGE",
            }),
            {
              status: 403,
              headers: { "Content-Type": "application/json", ...corsHeaders(request) },
            },
          );
        }
      }

      // Guard: if FASTAPI_ORIGIN is missing, return a clear 503
      if (!env.FASTAPI_ORIGIN) {
        return new Response(
          JSON.stringify({ error: "FASTAPI_ORIGIN not configured" }),
          {
            status: 503,
            headers: { "Content-Type": "application/json", ...corsHeaders(request) },
          },
        );
      }

      const origin = env.FASTAPI_ORIGIN.replace(/\/$/, "");
      const targetUrl = `${origin}${url.pathname}${url.search}`;
      const requestId = requestIdFor(request);

      // Clone and forward all original headers, fixing host + CF-Ray
      const forwardedHeaders = new Headers(request.headers);
      // Override host to match the target origin — Cloudflare rejects requests
      // whose Host header doesn't match the worker's own subdomain.
      forwardedHeaders.set("host", new URL(origin).host);
      forwardedHeaders.set("X-Request-ID", requestId);
      const cfRay = request.headers.get("CF-Ray");
      if (cfRay) {
        forwardedHeaders.set("CF-Ray", cfRay);
      }

      try {
        let response: Response;
        if (env.BACKEND) {
          // Preserve the client's exact path. FastAPI routes intentionally mix
          // trailing-slash and non-trailing-slash contracts, so changing the path
          // here can trigger an avoidable framework redirect.
          //
          // Redirects must remain manual at this boundary. OAuth authorization
          // and callback responses belong to the browser; following them inside
          // the service binding loses the public redirect and session cookie.
          const bindingRequest = new Request(targetUrl, {
            method: request.method,
            headers: forwardedHeaders,
            body: request.body,
            redirect: "manual",
            duplex: "half",
          } as unknown as RequestInit);
          response = await env.BACKEND.fetch(bindingRequest);
        } else {
          // Fallback: HTTP fetch; use redirect: "manual" so 307s pass through
          // to the client rather than being followed into a dead end.
          response = await fetch(targetUrl, {
            method: request.method,
            headers: forwardedHeaders,
            body: request.body,
            redirect: "manual",
            duplex: "half",
          } as unknown as RequestInit);
        }
        // Add CORS headers to every proxied response (including 500s).
        // Backend CORSMiddleware can't guarantee headers on error responses because
        // Starlette's ServerErrorMiddleware sits outside all user middleware — when a
        // 500 is thrown, the error response bypasses CORSMiddleware entirely. (issue #275)
        const finalResponse = new Response(response.body, response);
        const headers = corsHeaders(request);
        for (const [key, value] of Object.entries(headers)) {
          finalResponse.headers.set(key, value);
        }
        finalResponse.headers.set("X-Request-ID", requestId);
        console.log(
          JSON.stringify({
            event: "proxy_upstream_response",
            request_id: requestId,
            pathname: url.pathname,
            method: request.method,
            status: response.status,
          }),
        );
        return finalResponse;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(
          JSON.stringify({
            message: "upstream fetch failed",
            error: msg,
            target: targetUrl,
            pathname: url.pathname,
            method: request.method,
            request_id: requestId,
          }),
        );
        return new Response(
          JSON.stringify({
            error: "upstream fetch failed",
            detail: msg,
            target: targetUrl,
            request_id: requestId,
          }),
          {
            status: 502,
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": requestId,
              ...corsHeaders(request),
            },
          },
        );
      }
    },

    // ── Scheduled handler: clean up expired Matrix OAuth sessions ────────────
    // Runs hourly via Cloudflare Cron Trigger. Deletes expired OAuth states
    // and sessions from D1 to prevent accumulation (ADR-019).
    // No-op when DB binding is unavailable or ENABLE_MATRIX_AUTH is not set.
    async scheduled(
      _event: ScheduledEvent,
      env: Env,
      ctx: ExecutionContext,
    ): Promise<void> {
      if (!env.DB) return;

      const now = Math.floor(Date.now() / 1000);

      try {
        await env.DB.prepare(
          "DELETE FROM matrix_oauth_states WHERE expires_at < ?",
        )
          .bind(now)
          .run();

        await env.DB.prepare(
          "DELETE FROM matrix_oauth_sessions WHERE expires_at < ?",
        )
          .bind(now)
          .run();

        console.log(
          JSON.stringify({
            event: "session_cleanup",
            timestamp: now,
            status: "ok",
          }),
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(
          JSON.stringify({
            event: "session_cleanup",
            timestamp: now,
            status: "error",
            error: msg,
          }),
        );
      }
    },
  },
);
