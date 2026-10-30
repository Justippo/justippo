"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { checkHealth, type DemoFallbackData } from "@/lib/api-generated";

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

export type HealthStatus = "connecting" | "healthy" | "offline" | "error";

interface HealthState {
  readonly status: HealthStatus;
  readonly isOfflineMode: boolean;
  readonly fallbackData: DemoFallbackData | null;
  readonly retry: () => void;
}

export function useHealth(): HealthState {
  const [status, setStatus] = useState<HealthStatus>("connecting");
  const [isOfflineMode, setIsOfflineMode] = useState(false);
  const [fallbackData, setFallbackData] = useState<DemoFallbackData | null>(null);
  const attempted = useRef(false);
  const cancelledRef = useRef(false);

  const runCheck = useCallback(async () => {
    cancelledRef.current = false;
    setStatus("connecting");

    let retries = 0;
    while (retries < MAX_RETRIES) {
      if (cancelledRef.current) return;

      try {
        await checkHealth();
        if (!cancelledRef.current) {
          setStatus("healthy");
          setIsOfflineMode(false);
          setFallbackData(null);
        }
        return;
      } catch {
        // network error or timeout
      }

      retries++;
      if (retries < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        if (cancelledRef.current) return;
      }
    }

    if (cancelledRef.current) return;

    // All retries exhausted — fetch demo fallback
    let fallback: DemoFallbackData | null = null;
    try {
      const res = await fetch("/demo-fallback.json");
      if (res.ok) {
        fallback = await res.json();
      }
    } catch {
      // fallback fetch also failed
    }

    if (!cancelledRef.current) {
      if (fallback) {
        setStatus("offline");
        setIsOfflineMode(true);
        setFallbackData(fallback);
      } else {
        setStatus("error");
      }
    }
  }, []);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;
    runCheck();

    return () => {
      cancelledRef.current = true;
      attempted.current = false;
    };
  }, [runCheck]);

  const retry = useCallback(() => {
    attempted.current = false;
    runCheck();
  }, [runCheck]);

  return { status, isOfflineMode, fallbackData, retry };
}
