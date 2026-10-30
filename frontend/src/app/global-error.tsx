"use client";
// SPDX-License-Identifier: MIT

import { ErrorView } from "@/components/system";
import { useReportError } from "@/hooks/useReportError";

interface GlobalErrorProps {
  readonly error: Error & { digest?: string };
}

export default function GlobalError({ error }: Readonly<GlobalErrorProps>) {
  useReportError(error);

  return (
    <html lang="en">
      <body className="min-h-screen bg-surface font-sans antialiased">
        <ErrorView />
      </body>
    </html>
  );
}
