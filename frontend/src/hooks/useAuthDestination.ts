"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";

export function safeInternalRedirect(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return null;
  }
  return value;
}

interface AuthDestination {
  readonly destination: string;
  readonly loginHref: string;
  readonly registerHref: string;
}

export function useAuthDestination(defaultDestination: string): AuthDestination {
  const searchParams = useSearchParams();

  return useMemo(() => {
    const redirect = safeInternalRedirect(searchParams?.get("redirect") ?? null);
    const destination = redirect ?? defaultDestination;
    const suffix = redirect ? `?redirect=${encodeURIComponent(redirect)}` : "";

    return {
      destination,
      loginHref: `/login${suffix}`,
      registerHref: `/register${suffix}`,
    };
  }, [defaultDestination, searchParams]);
}
