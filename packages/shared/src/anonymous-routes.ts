export const PUBLIC_ONLY_ROUTES = ["/", "/login", "/register", "/onboarding", "/public", "/privacy", "/terms"] as const;

export const AUTH_AWARE_PUBLIC_ROUTES = ["/search", "/chat"] as const;

export const ANONYMOUS_ROUTES = [...PUBLIC_ONLY_ROUTES, ...AUTH_AWARE_PUBLIC_ROUTES] as const;

export function isPublicOnlyRoute(pathname: string): boolean {
  return (PUBLIC_ONLY_ROUTES as readonly string[]).includes(pathname);
}

export function isAuthAwarePublicRoute(pathname: string): boolean {
  return (AUTH_AWARE_PUBLIC_ROUTES as readonly string[]).includes(pathname);
}

export function shouldUseAnonymousLayout(pathname: string, isAuthenticated: boolean): boolean {
  if (isPublicOnlyRoute(pathname)) {
    // Landing page "/" switches to AuthenticatedLayout when authenticated
    // Other public-only routes (login, register, onboarding, public) always use AnonymousLayout
    if (pathname === "/") {
      return !isAuthenticated;
    }
    return true;
  }
  if (isAuthAwarePublicRoute(pathname)) {
    return !isAuthenticated;
  }
  return false;
}

/** @deprecated Use shouldUseAnonymousLayout — kept for tests migrating from S4 */
export function isAnonymousRoute(pathname: string): boolean {
  return (ANONYMOUS_ROUTES as readonly string[]).includes(pathname);
}