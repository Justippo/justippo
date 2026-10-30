"use client";

import { useCallback, useEffect } from "react";
import type { ChangeEvent } from "react";
import { useT } from "./useT";
import { DEFAULT_APP_LANGUAGE, isAppLanguage, type AppLanguage } from "@/lib/interface-language";

interface UseInterfaceLanguageResult {
  readonly language: AppLanguage;
  readonly onLanguageChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}

export function useInterfaceLanguage(): UseInterfaceLanguageResult {
  const { language, changeLanguage } = useT();
  const activeLanguage = isAppLanguage(language) ? language : DEFAULT_APP_LANGUAGE;

  useEffect(() => {
    document.documentElement.lang = activeLanguage;
  }, [activeLanguage]);

  const onLanguageChange = useCallback(
    (event: ChangeEvent<HTMLSelectElement>) => {
      const nextLanguage = event.target.value;
      if (isAppLanguage(nextLanguage)) {
        void changeLanguage(nextLanguage);
      }
    },
    [changeLanguage]
  );

  return {
    language: activeLanguage,
    onLanguageChange,
  };
}
