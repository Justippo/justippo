/**
 * Shared runtime configuration.
 * Single source of truth for API_BASE — consumed by api-generated client,
 * hooks, and any other module that needs the backend URL.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "https://evidence-eu-worker.mc146.workers.dev";

// ADR-019 deployment gate. Production builds enable the Matrix OAuth/PKCE flow.
export const MATRIX_AUTH_PREVIEW_ENABLED =
  process.env.NEXT_PUBLIC_MATRIX_AUTH_PREVIEW_ENABLED === "true";
