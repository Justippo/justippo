"use client";

import { usePathname } from "next/navigation";
import { AnonymousLayout, AuthenticatedLayout } from "@/components/layouts";
import { Spinner } from "@/components/atoms";
import { OfflineBanner } from "@/components/system";
import { isPublicOnlyRoute, shouldUseAnonymousLayout } from "@/lib/anonymous-routes";
import { useAuth } from "@/context/AuthContext";
import { useOfflineMode } from "@/context/OfflineModeContext";

interface AppShellProps {
  readonly children: React.ReactNode;
}

export function AppShell({ children }: Readonly<AppShellProps>) {
  const pathname = usePathname() ?? "/";
  const { isAuthenticated, isLoading } = useAuth();
  const { isOfflineMode } = useOfflineMode();

  const content = (
    <>
      {isOfflineMode && <OfflineBanner />}
      {children}
    </>
  );

  if (isLoading && !isPublicOnlyRoute(pathname)) {
    return (
      <main
        id="main-content"
        style={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}
      >
        <Spinner size="md" aria-label="Checking session" />
      </main>
    );
  }

  if (shouldUseAnonymousLayout(pathname, isAuthenticated)) {
    return <AnonymousLayout>{content}</AnonymousLayout>;
  }

  return <AuthenticatedLayout>{content}</AuthenticatedLayout>;
}
