"use client";

import { useAuth } from "@/context/AuthContext";
import { useRequireAuthRedirect } from "@/hooks/useRequireAuthRedirect";
import { Spinner } from "@/components/atoms";

interface RequireAuthProps {
  readonly children: React.ReactNode;
  readonly fallback?: React.ReactNode;
}

export function RequireAuth({ children, fallback }: Readonly<RequireAuthProps>) {
  const { isAuthenticated, isLoading } = useAuth();

  useRequireAuthRedirect({ enabled: !fallback && !isAuthenticated && !isLoading });

  if (isLoading) {
    return (
      <div role="status" aria-label="Checking session" className="p-xl text-center">
        <Spinner size="md" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return fallback ? <>{fallback}</> : null;
  }

  return <>{children}</>;
}
