"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

interface UseRequireAuthRedirectOptions {
  readonly enabled: boolean;
}

export function useRequireAuthRedirect({ enabled }: Readonly<UseRequireAuthRedirectOptions>): void {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/";

  useEffect(() => {
    if (enabled && !isLoading && !isAuthenticated) {
      const redirect = encodeURIComponent(pathname);
      router.replace(`/login?redirect=${redirect}`);
    }
  }, [enabled, isLoading, isAuthenticated, pathname, router]);
}
