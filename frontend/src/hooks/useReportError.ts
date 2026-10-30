"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export function useReportError(error: Error): void {
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
      Sentry.captureException(error);
    }
  }, [error]);
}
