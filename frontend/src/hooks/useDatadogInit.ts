"use client";

import { useEffect } from "react";
import { getLogsConfig, getRumConfig, isDatadogEnabled } from "@/lib/datadog-config";

export function useDatadogInit(): void {
  useEffect(() => {
    if (!isDatadogEnabled()) return;

    import("@datadog/browser-rum")
      .then(({ datadogRum }) => {
        datadogRum.init(getRumConfig(process.env.NODE_ENV));
        datadogRum.startSessionReplayRecording();
      })
      .catch(() => undefined);

    import("@datadog/browser-logs")
      .then(({ datadogLogs }) => {
        datadogLogs.init(getLogsConfig(process.env.NODE_ENV));
      })
      .catch(() => undefined);
  }, []);
}
