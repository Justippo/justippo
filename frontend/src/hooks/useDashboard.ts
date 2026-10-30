"use client";

import { useMemo } from "react";
import { useOfflineMode } from "@/context/OfflineModeContext";
import { DASHBOARD_ERROR_COPY, DASHBOARD_STATUS_BADGES } from "@/data/mockData";

export type DashboardViewState = "loading" | "success" | "error" | "empty";

interface UseDashboardOptions {
  readonly forcedState?: DashboardViewState;
}

interface DashboardStatusCard {
  readonly label: string;
  readonly badgeText: string;
  readonly badgeVariant: "success" | "warning" | "info";
}

interface UseDashboardResult {
  readonly viewState: DashboardViewState;
  readonly statusCards: readonly DashboardStatusCard[];
  readonly errorMessage: string | null;
  readonly retry: () => void;
}

export function useDashboard({
  forcedState,
}: Readonly<UseDashboardOptions> = {}): UseDashboardResult {
  const { status, retry } = useOfflineMode();

  return useMemo(() => {
    if (forcedState) {
      const forcedCards: readonly DashboardStatusCard[] =
        forcedState === "success" || forcedState === "empty"
          ? [
              { label: "API", badgeText: DASHBOARD_STATUS_BADGES.online, badgeVariant: "success" },
              {
                label: "Languages",
                badgeText: DASHBOARD_STATUS_BADGES.languages,
                badgeVariant: "info",
              },
            ]
          : [];

      return {
        viewState: forcedState,
        statusCards: forcedCards,
        errorMessage: forcedState === "error" ? DASHBOARD_ERROR_COPY.unavailable : null,
        retry,
      };
    }

    if (status === "connecting") {
      return {
        viewState: "loading" as const,
        statusCards: [],
        errorMessage: null,
        retry,
      };
    }

    if (status === "error") {
      return {
        viewState: "error" as const,
        statusCards: [],
        errorMessage: DASHBOARD_ERROR_COPY.unavailable,
        retry,
      };
    }

    return {
      viewState: "success" as const,
      statusCards: [
        {
          label: "API",
          badgeText:
            status === "healthy"
              ? DASHBOARD_STATUS_BADGES.online
              : DASHBOARD_STATUS_BADGES.unavailable,
          badgeVariant: status === "healthy" ? "success" : "warning",
        },
        {
          label: "Languages",
          badgeText: DASHBOARD_STATUS_BADGES.languages,
          badgeVariant: "info",
        },
      ],
      errorMessage: null,
      retry,
    };
  }, [forcedState, status, retry]);
}
