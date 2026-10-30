"use client";

import { ErrorView } from "@/components/system";
import { useReportError } from "@/hooks/useReportError";

interface ErrorPageProps {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}

export default function ErrorPage({ error, reset }: Readonly<ErrorPageProps>) {
  useReportError(error);

  return <ErrorView onRetry={reset} />;
}
