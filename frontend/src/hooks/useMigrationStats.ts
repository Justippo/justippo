"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/config";
import { GDPR_HEADERS } from "@/lib/api-generated";
import { parseEurostatResponse, type EurostatResponse, type MigrationStats } from "@/lib/eurostat";

export type MigrationStatsState = "loading" | "success" | "error" | "empty";

interface UseMigrationStatsResult {
  readonly viewState: MigrationStatsState;
  readonly stats: MigrationStats | null;
  readonly error: string | null;
  readonly retry: () => void;
}

export function useMigrationStats(): UseMigrationStatsResult {
  const [viewState, setViewState] = useState<MigrationStatsState>("loading");
  const [stats, setStats] = useState<MigrationStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  const fetchStats = useCallback(async () => {
    setViewState("loading");
    setError(null);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/stats/migration`, {
        headers: GDPR_HEADERS,
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const data: EurostatResponse = await resp.json();
      const parsed = parseEurostatResponse(data);

      if (parsed.countries.length === 0 && parsed.total === 0) {
        setViewState("empty");
        setStats(null);
        return;
      }

      setStats(parsed);
      setViewState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
      setViewState("error");
      setStats(null);
    }
  }, []);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats, retryCount]);

  const retry = useCallback(() => {
    setRetryCount((c) => c + 1);
  }, []);

  return { viewState, stats, error, retry };
}
