"use client";

import { useTolgee, useTranslate } from "@tolgee/react";
import { persistInterfaceLanguage, type AppLanguage } from "@/lib/interface-language";

interface UseTResult {
  readonly t: ReturnType<typeof useTranslate>["t"];
  readonly language: string;
  readonly changeLanguage: (language: AppLanguage) => Promise<void>;
}

/**
 * Thin wrapper around Tolgee — the only hook components should use for i18n.
 */
export function useT(): UseTResult {
  const { t } = useTranslate();
  const tolgee = useTolgee();

  return {
    t,
    language: tolgee.getLanguage() ?? "en",
    changeLanguage: async (language: AppLanguage) => {
      await tolgee.changeLanguage(language);
      persistInterfaceLanguage(language);
    },
  };
}
