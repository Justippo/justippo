// SPDX-License-Identifier: MIT
/**
 * TolgeeClientProvider — client-side Tolgee provider wrapper.
 *
 * Wraps the entire app ONCE in layout.tsx. This is the only place
 * TolgeeProvider is mounted — DRY: no per-component providers.
 *
 * useMemo: prevents creating a new Tolgee instance on every render.
 */
"use client";

import { TolgeeProvider } from "@tolgee/react";
import { staticData, tolgeeConfig } from "@/lib/tolgee";
import type { ReactNode } from "react";
import { useTolgeeClient } from "@/hooks/useTolgeeClient";

interface TolgeeClientProviderProps {
  readonly children: ReactNode;
}

export function TolgeeClientProvider({ children }: Readonly<TolgeeClientProviderProps>) {
  const tolgee = useTolgeeClient();
  const initialLanguage = tolgee.getLanguage() ?? tolgeeConfig.defaultLanguage;

  return (
    <TolgeeProvider
      tolgee={tolgee}
      fallback="Loading\u2026"
      ssr={{ language: initialLanguage, staticData }}
    >
      {children}
    </TolgeeProvider>
  );
}
