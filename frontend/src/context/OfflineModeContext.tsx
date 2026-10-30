"use client";

import { createContext, useContext, useMemo } from "react";
import type { DemoFallbackData } from "@/lib/api-generated";
import type { HealthStatus } from "@/hooks/useHealth";

export interface OfflineModeValue {
  readonly status: HealthStatus;
  readonly isOfflineMode: boolean;
  readonly fallbackData: DemoFallbackData | null;
  readonly retry: () => void;
}

const OfflineModeContext = createContext<OfflineModeValue>({
  status: "connecting",
  isOfflineMode: false,
  fallbackData: null,
  retry: () => {},
});

interface OfflineModeProviderProps {
  readonly children: React.ReactNode;
  readonly status: HealthStatus;
  readonly isOfflineMode: boolean;
  readonly fallbackData: DemoFallbackData | null;
  readonly retry: () => void;
}

export function OfflineModeProvider({
  children,
  status,
  isOfflineMode,
  fallbackData,
  retry,
}: Readonly<OfflineModeProviderProps>) {
  const value = useMemo(
    () => ({ status, isOfflineMode, fallbackData, retry }),
    [status, isOfflineMode, fallbackData, retry]
  );
  return <OfflineModeContext.Provider value={value}>{children}</OfflineModeContext.Provider>;
}

export function useOfflineMode(): OfflineModeValue {
  return useContext(OfflineModeContext);
}
