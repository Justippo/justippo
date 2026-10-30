"use client";

import { OfflineModeProvider } from "@/context/OfflineModeContext";
import { useHealth } from "@/hooks/useHealth";

interface ConnectingOverlayProps {
  readonly children: React.ReactNode;
}

/**
 * Silent background health check — warms the API on mount and provides demo
 * fallback context. Intentionally renders no visible overlay or connecting copy.
 */
export function ConnectingOverlay({ children }: Readonly<ConnectingOverlayProps>) {
  const { status, isOfflineMode, fallbackData, retry } = useHealth();

  return (
    <OfflineModeProvider
      status={status}
      isOfflineMode={isOfflineMode}
      fallbackData={fallbackData}
      retry={retry}
    >
      {children}
    </OfflineModeProvider>
  );
}
