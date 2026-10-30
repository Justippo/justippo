"use client";

/**
 * MOBILE_GAP: This PKCE flow uses window.location for redirect.
 * Mobile requires expo-auth-session. See ADR-019 and
 * docs/mobile/mobile-compat.md for the adaptation plan.
 */

import { useState, useEffect, useCallback } from "react";
import { API_BASE, MATRIX_AUTH_PREVIEW_ENABLED } from "@/lib/config";
import { DEMO_EMAIL, DEMO_PASSWORD } from "@evidenceeu/shared";

const AUTH_STORAGE_KEY = "evidenceeu_auth";
const AUTH_RETURN_PATH_KEY = "evidenceeu_auth_return_path";
const SESSION_CACHE_KEY = "evidenceeu_session_v1";
const AUTH_COOKIE_NAME = "evidenceeu_auth_token";
const AUTH_CHANNEL_NAME = "evidenceeu_auth";
const CACHE_TTL_MS = 5 * 60 * 1000;

let _authChannel: BroadcastChannel | null = null;
function getAuthChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  if (!_authChannel) {
    try {
      _authChannel = new BroadcastChannel(AUTH_CHANNEL_NAME);
    } catch {
      return null;
    }
  }
  return _authChannel;
}

interface CachedSession {
  readonly authenticated: boolean;
}

function getCachedSession(): CachedSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) return null;
    const { session, expiresAt } = JSON.parse(raw);
    if (Date.now() > expiresAt) {
      sessionStorage.removeItem(SESSION_CACHE_KEY);
      return null;
    }
    return session as CachedSession;
  } catch {
    return null;
  }
}

function setCachedSession(session: CachedSession): void {
  try {
    sessionStorage.setItem(
      SESSION_CACHE_KEY,
      JSON.stringify({ session, expiresAt: Date.now() + CACHE_TTL_MS })
    );
  } catch {
    // sessionStorage unavailable
  }
}

function clearCachedSession(): void {
  try {
    sessionStorage.removeItem(SESSION_CACHE_KEY);
  } catch {
    // sessionStorage unavailable
  }
}

function setAuthCookie(): void {
  try {
    document.cookie = `${AUTH_COOKIE_NAME}=true; path=/; max-age=31536000; SameSite=Lax`;
  } catch {
    // cookies unavailable
  }
}

function clearAuthCookie(): void {
  try {
    document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`;
  } catch {
    // cookies unavailable
  }
}

/**
 * DRY: Clear all client-side auth storage in one call.
 * Used by logout(), cross-tab logout sync, and bfcache revalidation.
 */
function clearAllAuthStorage(): void {
  clearCachedSession();
  clearAuthCookie();
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // localStorage unavailable
  }
}

interface AuthState {
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
  readonly isMatrixAuthEnabled: boolean;
  readonly login: () => void;
  readonly loginWithCredentials: (email: string, password: string, returnPath?: string) => boolean;
  readonly logout: () => Promise<void>;
}

export function useAuthState(): AuthState {
  // Initial render must be deterministic across server and client to avoid a
  // hydration mismatch: sessionStorage is unavailable during SSR but populated
  // on the client's first render. Start unauthenticated/loading, then hydrate
  // the cached session in the effect below (post-hydration, client-only).
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const cached = getCachedSession();
    if (cached) {
      setIsAuthenticated(cached.authenticated);
      setIsLoading(false);
      return;
    }
    if (MATRIX_AUTH_PREVIEW_ENABLED) {
      const controller = new AbortController();
      // cache: "no-store" prevents Safari/WebKit from serving a stale cached
      // "authenticated: true" response after logout. Without this, Safari's HTTP
      // cache re-authenticates the user on page refresh following sign-out.
      void fetch(`${API_BASE}/api/v1/auth/matrix/session`, {
        credentials: "include",
        cache: "no-store",
        signal: controller.signal,
      })
        .then((response) => (response.ok ? response.json() : { authenticated: false }))
        .then((session: { authenticated?: boolean }) => {
          if (controller.signal.aborted) return;
          const authenticated = session.authenticated === true;
          setIsAuthenticated(authenticated);
          if (authenticated) {
            setCachedSession(session as CachedSession);
            setAuthCookie();
            try {
              const returnPath = sessionStorage.getItem(AUTH_RETURN_PATH_KEY);
              sessionStorage.removeItem(AUTH_RETURN_PATH_KEY);
              if (
                returnPath?.startsWith("/") &&
                !returnPath.startsWith("//") &&
                !returnPath.includes("\\") &&
                returnPath !== window.location.pathname
              ) {
                window.location.replace(returnPath);
              }
            } catch {
              // sessionStorage unavailable; the backend dashboard redirect remains valid.
            }
          } else {
            clearAllAuthStorage();
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setIsAuthenticated(false);
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsLoading(false);
        });
      return () => controller.abort();
    }
    try {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      const authenticated = stored === "true";
      setIsAuthenticated(authenticated);
      if (authenticated) {
        setCachedSession({ authenticated: true });
        setAuthCookie();
      } else {
        clearAllAuthStorage();
      }
    } catch {
      // localStorage unavailable (SSR or privacy mode)
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    const channel = getAuthChannel();
    const handler = (event: MessageEvent<{ type: string }>) => {
      if (event.data?.type === "logout") {
        setIsAuthenticated(false);
        clearAllAuthStorage();
      }
    };
    channel?.addEventListener("message", handler);
    return () => channel?.removeEventListener("message", handler);
  }, []);

  // Safari/WebKit bfcache: when a page is restored from the back-forward
  // cache, JS state is frozen from the prior visit. If the user logged out in
  // another tab (or navigated away after logout), the frozen isAuthenticated
  // state is stale. Revalidate from sessionStorage on pageshow(persisted).
  useEffect(() => {
    const onPageshow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      const cached = getCachedSession();
      if (!cached || !cached.authenticated) {
        setIsAuthenticated(false);
        clearAllAuthStorage();
      }
    };
    window.addEventListener("pageshow", onPageshow);
    return () => window.removeEventListener("pageshow", onPageshow);
  }, []);

  const login = useCallback(() => {
    setIsAuthenticated(true);
    setCachedSession({ authenticated: true });
    setAuthCookie();
    try {
      localStorage.setItem(AUTH_STORAGE_KEY, "true");
    } catch {
      // localStorage unavailable
    }
  }, []);

  const loginWithCredentials = useCallback(
    (email: string, password: string, returnPath = "/dashboard"): boolean => {
      if (MATRIX_AUTH_PREVIEW_ENABLED) {
        if (
          returnPath.startsWith("/") &&
          !returnPath.startsWith("//") &&
          !returnPath.includes("\\")
        ) {
          try {
            sessionStorage.setItem(AUTH_RETURN_PATH_KEY, returnPath);
          } catch {
            // sessionStorage unavailable; the backend dashboard redirect remains valid.
          }
        }
        window.location.assign(`${API_BASE}/api/v1/auth/matrix/login`);
        return true;
      }
      const normalizedEmail = email.trim().toLowerCase();
      if (normalizedEmail === DEMO_EMAIL && password === DEMO_PASSWORD) {
        login();
        return true;
      }
      return false;
    },
    [login]
  );

  const logout = useCallback(async () => {
    // Set loading true so RequireAuth guards don't render authenticated
    // content during the async backend teardown.  The HttpOnly session cookie
    // can only be cleared by the backend, so we must await the fetch before
    // any navigation/refresh can trigger a session check.
    setIsLoading(true);
    getAuthChannel()?.postMessage({ type: "logout" });
    if (MATRIX_AUTH_PREVIEW_ENABLED) {
      // keepalive: true ensures the request survives page unload (e.g., when
      // logout is immediately followed by router.replace("/")).  cache:
      // "no-store" prevents Safari from caching the logout response.
      try {
        await fetch(`${API_BASE}/api/v1/auth/matrix/logout`, {
          method: "POST",
          credentials: "include",
          cache: "no-store",
          keepalive: true,
          headers: { "X-GDPR-Consent": "auth-session" },
        });
      } catch {
        // Backend unreachable; clear client state anyway so the user is
        // signed out locally.  The HttpOnly cookie will expire naturally.
      }
    }
    setIsAuthenticated(false);
    clearAllAuthStorage();
    setIsLoading(false);
  }, []);

  return {
    isAuthenticated,
    isLoading,
    isMatrixAuthEnabled: MATRIX_AUTH_PREVIEW_ENABLED,
    login,
    loginWithCredentials,
    logout,
  };
}
